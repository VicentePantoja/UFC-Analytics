import time
import random
from pathlib import Path
from typing import List

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

try:
    from urllib3.util import Retry
except ImportError:
    from requests.packages.urllib3.util.retry import Retry

BASE_URL = "http://ufcstats.com"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "Data" / "ufc_fights.csv"

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
                    print(f"[WARN] HTTPS failed. Attempting with HTTP: {alt_url}")
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


def load_existing_urls() -> set:
    if OUTPUT_FILE.exists():
        df = pd.read_csv(OUTPUT_FILE, dtype=str)
        return set(df["fighter_url"].dropna().tolist())
    return set()


def save_urls(urls: List[str]) -> None:
    df = pd.DataFrame({"fighter_url": sorted(urls)})
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")


def scrape_letter(session: requests.Session, letter: str) -> List[str]:
    url = f"{BASE_URL}/statistics/fighters?char={letter}&page=all"
    try:
        response = safe_get(url, session)
        soup = BeautifulSoup(response.text, "html.parser")
        urls = []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if "/fighter-details/" in href:
                if href.startswith("/"):
                    href = BASE_URL + href
                if href not in urls:
                    urls.append(href)
        return urls
    except Exception as exc:
        print(f"[ERROR] Failed to scrape letter '{letter}': {exc}")
        return []


def main() -> None:
    print("Starting UFC fighter URL scraper.")
    print(f"Output file: {OUTPUT_FILE}")

    session = create_session()
    existing_urls = load_existing_urls()
    print(f"Already saved: {len(existing_urls)} URLs")

    all_urls = set(existing_urls)
    letters = "abcdefghijklmnopqrstuvwxyz"

    for letter in letters:
        print(f"\n[{letter.upper()}] Scraping fighters...")
        letter_urls = scrape_letter(session, letter)
        new_urls = [u for u in letter_urls if u not in all_urls]
        all_urls.update(new_urls)
        print(f"  Found {len(letter_urls)} total, {len(new_urls)} new.")
        save_urls(list(all_urls))
        time.sleep(random.uniform(1.0, 2.0))

    print(f"\nDone. Total fighter URLs saved: {len(all_urls)}")
    print(f"File saved at: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
