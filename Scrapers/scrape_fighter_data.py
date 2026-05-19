import re
import time
import random
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

try:
    from urllib3.util import Retry
except ImportError:
    from requests.packages.urllib3.util.retry import Retry

BASE_URL = "http://ufcstats.com"
URLS_FILE = Path(__file__).resolve().parent.parent / "Data" / "ufc_fighter_urls.csv"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "Data" / "ufc_fighters.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "max-age=0",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

COLUMNS = [
    "fighter_url",
    "fighter_name",
    "nickname",
    "height_cm",
    "weight_lbs",
    "reach_cm",
    "stance",
    "date_of_birth",
    "wins",
    "losses",
    "draws",
    "no_contests",
    "slpm",
    "str_acc",
    "sapm",
    "str_def",
    "td_avg",
    "td_acc",
    "td_def",
    "sub_avg",
]


def create_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


def safe_get(url: str, session: requests.Session, timeout: int = 30) -> requests.Response:
    for attempt in range(1, 6):
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            if attempt == 5:
                if url.startswith("https://"):
                    alt_url = url.replace("https://", "http://", 1)
                    try:
                        response = session.get(alt_url, timeout=timeout)
                        response.raise_for_status()
                        return response
                    except requests.RequestException:
                        raise
                raise
            wait = 1.5 * attempt
            print(f"[WARN] Request failed ({attempt}/5) for {url}: {exc}")
            time.sleep(wait)
    raise RuntimeError(f"Unable to fetch URL after retries: {url}")


def normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def parse_height(value: str) -> Optional[str]:
    value = normalize_text(value)
    if not value or value == "--":
        return ""
    match = re.match(r"(\d+)'?\s*(\d+)\"?", value)
    if match:
        feet = int(match.group(1))
        inches = int(match.group(2))
        cm = round((feet * 12 + inches) * 2.54)
        return str(cm)
    return ""


def parse_reach(value: str) -> Optional[str]:
    value = normalize_text(value)
    if not value or value == "--":
        return ""
    match = re.match(r"(\d+\.?\d*)", value)
    if match:
        inches = float(match.group(1))
        cm = round(inches * 2.54)
        return str(cm)
    return ""


def parse_weight(value: str) -> Optional[str]:
    value = normalize_text(value)
    if not value or value == "--":
        return ""
    match = re.match(r"(\d+)", value)
    return match.group(1) if match else ""


def parse_percentage(value: str) -> str:
    value = normalize_text(value).replace("%", "").strip()
    if not value or value == "--":
        return ""
    try:
        return str(round(float(value) / 100, 4))
    except ValueError:
        return ""


def parse_float(value: str) -> str:
    value = normalize_text(value)
    if not value or value == "--":
        return ""
    try:
        return str(float(value))
    except ValueError:
        return ""


def parse_record(record_text: str) -> Dict[str, str]:
    result = {"wins": "", "losses": "", "draws": "", "no_contests": ""}
    match = re.search(r"(\d+)-(\d+)-(\d+)(?:\s*\((\d+)\s*NC\))?", record_text)
    if match:
        result["wins"] = match.group(1)
        result["losses"] = match.group(2)
        result["draws"] = match.group(3)
        result["no_contests"] = match.group(4) or "0"
    return result


def scrape_fighter(session: requests.Session, url: str) -> Optional[Dict[str, str]]:
    try:
        response = safe_get(url, session)
        soup = BeautifulSoup(response.text, "html.parser")

        # Name
        name_tag = soup.select_one("span.b-content__title-highlight")
        if not name_tag:
            name_tag = soup.select_one("h1.b-content__title")
        fighter_name = normalize_text(name_tag.get_text()) if name_tag else ""

        # Nickname
        nick_tag = soup.select_one("p.b-content__Nickname")
        nickname = normalize_text(nick_tag.get_text()) if nick_tag else ""

        # Record
        record_tag = soup.select_one("span.b-content__title-record")
        record = parse_record(record_tag.get_text() if record_tag else "")

        # Physical stats
        physical = {}
        for li in soup.select("li.b-list__box-list-item"):
            text = normalize_text(li.get_text(" "))
            if "Height:" in text:
                physical["height"] = text.split("Height:")[-1].strip()
            elif "Weight:" in text:
                physical["weight"] = text.split("Weight:")[-1].strip()
            elif "Reach:" in text:
                physical["reach"] = text.split("Reach:")[-1].strip()
            elif "STANCE:" in text or "Stance:" in text:
                physical["stance"] = text.split(":")[-1].strip()
            elif "DOB:" in text or "Date of birth:" in text.lower():
                physical["dob"] = text.split(":")[-1].strip()

        # Career stats
        career = {}
        for li in soup.select("li.b-list__box-list-item_type_block"):
            text = normalize_text(li.get_text(" "))
            for key, label in [
                ("slpm", "SLpM:"),
                ("str_acc", "Str. Acc.:"),
                ("sapm", "SApM:"),
                ("str_def", "Str. Def:"),
                ("td_avg", "TD Avg.:"),
                ("td_acc", "TD Acc.:"),
                ("td_def", "TD Def.:"),
                ("sub_avg", "Sub. Avg.:"),
            ]:
                if label in text:
                    career[key] = text.split(label)[-1].strip()

        return {
            "fighter_url": url,
            "fighter_name": fighter_name,
            "nickname": nickname,
            "height_cm": parse_height(physical.get("height", "")),
            "weight_lbs": parse_weight(physical.get("weight", "")),
            "reach_cm": parse_reach(physical.get("reach", "")),
            "stance": physical.get("stance", ""),
            "date_of_birth": physical.get("dob", ""),
            "wins": record["wins"],
            "losses": record["losses"],
            "draws": record["draws"],
            "no_contests": record["no_contests"],
            "slpm": parse_float(career.get("slpm", "")),
            "str_acc": parse_percentage(career.get("str_acc", "")),
            "sapm": parse_float(career.get("sapm", "")),
            "str_def": parse_percentage(career.get("str_def", "")),
            "td_avg": parse_float(career.get("td_avg", "")),
            "td_acc": parse_percentage(career.get("td_acc", "")),
            "td_def": parse_percentage(career.get("td_def", "")),
            "sub_avg": parse_float(career.get("sub_avg", "")),
        }

    except Exception as exc:
        print(f"  [ERROR] Failed to scrape {url}: {exc}")
        return None


def load_existing_data() -> pd.DataFrame:
    if OUTPUT_FILE.exists():
        df = pd.read_csv(OUTPUT_FILE, dtype=str, encoding="utf-8", keep_default_na=False)
        for col in COLUMNS:
            if col not in df.columns:
                df[col] = ""
        return df[COLUMNS]
    return pd.DataFrame(columns=COLUMNS)


def save_data(df: pd.DataFrame) -> None:
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")


def main() -> None:
    print("Starting UFC fighter data scraper.")
    print(f"Input:  {URLS_FILE}")
    print(f"Output: {OUTPUT_FILE}")

    if not URLS_FILE.exists():
        print(f"[ERROR] URLs file not found: {URLS_FILE}")
        print("Run scrape_fighter_urls.py first.")
        return

    urls_df = pd.read_csv(URLS_FILE, dtype=str)
    all_urls = urls_df["fighter_url"].dropna().tolist()
    print(f"Total fighter URLs: {len(all_urls)}")

    existing_df = load_existing_data()
    existing_urls = set(existing_df["fighter_url"].tolist())
    print(f"Already scraped: {len(existing_urls)}")

    pending_urls = [u for u in all_urls if u not in existing_urls]
    print(f"Pending: {len(pending_urls)}")

    if not pending_urls:
        print("All fighters already scraped.")
        return

    session = create_session()
    rows = existing_df.to_dict(orient="records")

    for i, url in enumerate(pending_urls, start=1):
        print(f"[{i}/{len(pending_urls)}] {url}")
        data = scrape_fighter(session, url)
        if data:
            rows.append(data)
            print(f"  -> {data['fighter_name']} | {data['wins']}W-{data['losses']}L | Height: {data['height_cm']}cm | Reach: {data['reach_cm']}cm")
        else:
            print(f"  -> Skipped.")

        if i % 50 == 0:
            save_data(pd.DataFrame(rows, columns=COLUMNS))
            print(f"  [Saved progress: {len(rows)} fighters]")

        time.sleep(random.uniform(0.8, 1.8))

    save_data(pd.DataFrame(rows, columns=COLUMNS))
    print(f"\nDone. Total fighters saved: {len(rows)}")
    print(f"File saved at: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
