"""
Scrapes UFC champion history from Wikipedia.
Source: https://en.wikipedia.org/wiki/List_of_UFC_champions
Output: Data/ufc_champions.csv

For each champion, the script:
1. Scrapes the main UFC champions page for basic info (reign, event, date, days)
2. Visits each champion's individual Wikipedia page to count accurate title defenses

Note: Wikipedia rate limits requests. Run the script multiple times if needed —
it will only update defenses where it finds a better value than what is already stored.
"""
import re
import time
import random
from pathlib import Path
from typing import List, Dict, Optional
from urllib.parse import quote

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

try:
    from urllib3.util import Retry
except ImportError:
    from requests.packages.urllib3.util.retry import Retry

URL = "https://en.wikipedia.org/wiki/List_of_UFC_champions"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "Data" / "ufc_champions.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

COLUMNS = [
    "division",
    "reign_number",
    "champion",
    "defeated",
    "event_won",
    "date_won",
    "reign_days",
    "defenses_count",
    "defense_details",
]

SKIP = ["contents", "references", "external", "notes", "see also",
        "men's championship", "women's championship", "nationality", "wins by",
        "championship wins"]

NAME_OVERRIDES = {
    "BJ Penn": "B.J._Penn",
    "B.J. Penn": "B.J._Penn",
    "TJ Dillashaw": "T.J._Dillashaw",
    "T.J. Dillashaw": "T.J._Dillashaw",
    "CM Punk": "CM_Punk",
}


def create_session() -> requests.Session:
    session = requests.Session()
    # No automatic retries — we handle manually to avoid hammering Wikipedia
    adapter = HTTPAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


def normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def clean(text: str) -> str:
    return re.sub(r"\[.*?\]", "", normalize_text(text)).strip()


def parse_reign_days(value: str) -> str:
    value = clean(value)
    match = re.search(r"(\d+)\+?\s*days?", value, re.I)
    return match.group(1) if match else ""


def parse_defenses_from_cell(cell) -> tuple:
    spans = cell.find_all("span")
    defense_lines = []
    for span in spans:
        text = normalize_text(span.get_text(" "))
        text = re.sub(r"\[.*?\]", "", text).strip()
        if re.match(r"^\d+\.", text):
            defense_lines.append(text)
    count = str(len(defense_lines)) if defense_lines else "0"
    details = " | ".join(defense_lines)
    return count, details


def name_to_wiki_url(name: str) -> str:
    if name in NAME_OVERRIDES:
        slug = NAME_OVERRIDES[name]
    else:
        slug = name.replace(" ", "_")
    return f"https://en.wikipedia.org/wiki/{quote(slug, safe='_.-')}"


def get_search_terms(division: str) -> list:
    keyword = division.replace(" Championship", "").strip()
    if "Women" in division:
        return [
            f"UFC {keyword} Championship",
            f"UFC {keyword} World Championship",
        ]
    else:
        exact_divisions = {
            "Heavyweight": "UFC Heavyweight Championship",
            "Flyweight": "UFC Flyweight Championship",
            "Bantamweight": "UFC Bantamweight Championship",
            "Featherweight": "UFC Featherweight Championship",
        }
        keyword_clean = keyword.replace("Women's ", "").strip()
        return [exact_divisions.get(keyword_clean, f"UFC {keyword_clean} Championship")]


def get_defenses_from_wiki(session: requests.Session, champion: str, division: str) -> Optional[int]:
    """Visit champion's Wikipedia page and count accurate UFC title defenses for the division."""
    url = name_to_wiki_url(champion)
    try:
        response = session.get(url, timeout=8)
        if response.status_code in [403, 429]:
            print(f" [RATE LIMITED]")
            time.sleep(10)
            return None
        if response.status_code == 404:
            print(f" [404]")
            return None
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        fight_table = None
        for table in soup.find_all("table", class_="wikitable"):
            headers = [th.get_text(strip=True) for th in table.find_all("th")]
            if "Opponent" in headers and "Method" in headers:
                fight_table = table
                break

        if not fight_table:
            print(f" [NO TABLE]")
            return None

        search_terms = get_search_terms(division)
        defenses = 0
        for row in fight_table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            notes = cells[-1].get_text(" ", strip=True)
            if "Defended" in notes and any(t.lower() in notes.lower() for t in search_terms):
                defenses += 1

        return defenses

    except requests.Timeout:
        print(f" [TIMEOUT]")
        return None
    except Exception as exc:
        print(f" [ERROR: {exc}]")
        return None


def parse_table(table, division: str) -> List[Dict[str, str]]:
    records = []
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        if cells[0].get_text(strip=True) in {"No.", "No", ""}:
            continue
        if len(cells) < 5 or cells[0].get("colspan"):
            continue

        reign_number = clean(cells[0].get_text())
        if not reign_number.isdigit():
            continue

        name_cell = cells[1]
        name_link = None
        for a in name_cell.find_all("a"):
            if a.get_text(strip=True):
                name_link = a
                break
        champion = clean(name_link.get_text()) if name_link else clean(name_cell.get_text().split("\n")[0])

        defeated_tag = name_cell.find("small")
        if defeated_tag:
            defeated = clean(defeated_tag.get_text()).replace("def.", "").strip()
        else:
            def_match = re.search(r"def\.\s*(.+)", clean(name_cell.get_text()))
            defeated = def_match.group(1).strip() if def_match else ""

        event_cell = cells[2]
        event_link = event_cell.find("a")
        event_won = clean(event_link.get_text()) if event_link else clean(event_cell.get_text().split("\n")[0])

        date_won = clean(cells[3].get_text())
        reign_days = parse_reign_days(cells[4].get_text()) if len(cells) > 4 else ""

        if len(cells) > 5:
            defenses_count, defense_details = parse_defenses_from_cell(cells[5])
        else:
            defenses_count, defense_details = "0", ""

        records.append({
            "division": division,
            "reign_number": reign_number,
            "champion": champion,
            "defeated": defeated,
            "event_won": event_won,
            "date_won": date_won,
            "reign_days": reign_days,
            "defenses_count": defenses_count,
            "defense_details": defense_details,
        })
    return records


def scrape_history(soup: BeautifulSoup) -> List[Dict[str, str]]:
    elements = []
    for el in soup.find_all(["div", "table"]):
        if el.name == "div" and "mw-heading" in " ".join(el.get("class", [])):
            h = el.find(["h2", "h3"])
            if h:
                text = clean(h.get_text())
                elements.append(("heading", text, el))
        elif el.name == "table" and "wikitable" in " ".join(el.get("class", [])):
            elements.append(("table", "", el))

    table_count = 0
    records = []
    current_division = ""

    for typ, text, el in elements:
        if typ == "heading":
            if any(s in text.lower() for s in SKIP):
                current_division = ""
            elif "championship" in text.lower() or "grand prix" in text.lower():
                current_division = text
            else:
                current_division = ""
        elif typ == "table":
            table_count += 1
            if table_count <= 2:
                continue
            if not current_division:
                continue
            parsed = parse_table(el, current_division)
            records.extend(parsed)
            print(f"  {current_division}: {len(parsed)} records")

    return records


def update_defenses(session: requests.Session, df: pd.DataFrame) -> pd.DataFrame:
    """
    Update defenses_count by visiting each champion's Wikipedia page.
    Only overwrites existing value if the new value is greater than 0.
    This way running the script multiple times keeps improving the data.
    """
    print("\nUpdating defenses from individual Wikipedia pages...")
    updated = 0
    skipped = 0
    failed = 0

    for idx, row in df.iterrows():
        champion = row["champion"].strip()
        division = row["division"].strip()
        if not champion:
            continue

        existing = int(row["defenses_count"]) if str(row["defenses_count"]).isdigit() else 0
        print(f"  [{idx+1}/{len(df)}] {champion} — {division} (current: {existing})", end=" ")

        defenses = get_defenses_from_wiki(session, champion, division)

        if defenses is not None and defenses > 0:
            df.at[idx, "defenses_count"] = str(defenses)
            print(f"-> updated to {defenses}")
            updated += 1
        elif defenses == 0 and existing > 0:
            # Don't overwrite a good value with 0 (likely a failed request)
            print(f"-> kept {existing} (Wikipedia returned 0, keeping existing)")
            skipped += 1
        else:
            print(f"-> kept {existing}")
            failed += 1

        # Save after every 10 records to preserve progress
        if (idx + 1) % 10 == 0:
            df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")

        time.sleep(random.uniform(2.5, 4.5))

    print(f"\nDefenses updated: {updated}, kept existing: {skipped}, failed: {failed}")
    return df


def main() -> None:
    print("Starting UFC champions scraper.")
    print(f"Source: {URL}")
    print(f"Output: {OUTPUT_FILE}")

    session = create_session()

    # Step 1 — Scrape main champions page
    print("\nStep 1: Fetching main champions page...")
    response = session.get(URL, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    history = scrape_history(soup)
    df = pd.DataFrame(history, columns=COLUMNS)
    print(f"Total records: {len(df)} | Divisions: {df['division'].nunique()}")

    # Step 2 — Update defenses from individual pages
    df = update_defenses(session, df)

    # Save final
    df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
    print(f"\nTop 10 defenders:")
    df['defenses_count'] = pd.to_numeric(df['defenses_count'], errors='coerce').fillna(0)
    max_def = df.groupby(['champion', 'division'])['defenses_count'].max().reset_index()
    total = max_def.groupby('champion')['defenses_count'].sum().sort_values(ascending=False).head(10)
    print(total.to_string())
    print(f"\nSaved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
