import re
import time
import random
from pathlib import Path
from typing import Dict, List

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

try:
    from urllib3.util import Retry
except ImportError:
    from requests.packages.urllib3.util.retry import Retry

BASE_URL = "http://ufcstats.com"
EVENTS_URL = f"{BASE_URL}/statistics/events/completed?page=all"
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

COLUMNS = [
    "event_date",
    "event_name",
    "event_location",
    "event_url",
    "fight_url",
    "weight_class",
    "fighter_1",
    "fighter_2",
    "winner",
    "method",
    "round",
    "time",
    "scheduled_rounds",
    "knockdowns_1",
    "knockdowns_2",
    "total_strikes_landed_1",
    "total_strikes_att_1",
    "total_strikes_landed_2",
    "total_strikes_att_2",
    "significant_strikes_landed_1",
    "significant_strikes_att_1",
    "significant_strikes_landed_2",
    "significant_strikes_att_2",
    "sig_strikes_head_1",
    "sig_strikes_head_2",
    "sig_strikes_body_1",
    "sig_strikes_body_2",
    "sig_strikes_leg_1",
    "sig_strikes_leg_2",
    "distance_strikes_1",
    "distance_strikes_2",
    "clinch_strikes_1",
    "clinch_strikes_2",
    "ground_strikes_1",
    "ground_strikes_2",
    "sig_strikes_accuracy_1",
    "sig_strikes_accuracy_2",
    "sig_strikes_defense_1",
    "sig_strikes_defense_2",
    "takedowns_att_1",
    "takedowns_succ_1",
    "takedowns_att_2",
    "takedowns_succ_2",
    "takedowns_pct_1",
    "takedowns_pct_2",
    "takedowns_defense_1",
    "takedowns_defense_2",
    "control_time_seconds_1",
    "control_time_seconds_2",
    "subs_att_1",
    "subs_att_2",
    "reversals_1",
    "reversals_2",
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


def normalize_text(value: str) -> str:
    return " ".join(value.split()).strip()


def normalize_header(header: str) -> str:
    normalized = normalize_text(header).replace('.', '')
    normalized = normalized.replace('%', ' %')
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.lower()


def split_dual_values(value: str) -> (str, str):
    values = normalize_text(value).split()
    if not values:
        return "", ""
    mid = len(values) // 2
    return " ".join(values[:mid]), " ".join(values[mid:])


def parse_int(value: str) -> int:
    value = normalize_text(value)
    if not value or value == '---':
        return 0
    try:
        return int(value)
    except ValueError:
        match = re.search(r"(\d+)", value)
        return int(match.group(1)) if match else 0


def parse_time_seconds(value: str) -> str:
    value = normalize_text(value)
    match = re.match(r"^(\d+):(\d{2})$", value)
    if match:
        minutes = int(match.group(1))
        seconds = int(match.group(2))
        return str(minutes * 60 + seconds)
    return "0"


def parse_count_pair(value: str) -> Dict[str, str]:
    value = normalize_text(value)
    match = re.match(r"^(\d+)\s*of\s*(\d+)$", value, flags=re.I)
    if match:
        return {"made": match.group(1), "attempts": match.group(2)}
    return {"made": value if value and value != '---' else '0', "attempts": '0'}


def add_sum(stats: Dict[str, str], key_base: str, value_1: str, value_2: str) -> None:
    stats[f"{key_base}_1"] = str(parse_int(stats.get(f"{key_base}_1", "0")) + parse_int(value_1))
    stats[f"{key_base}_2"] = str(parse_int(stats.get(f"{key_base}_2", "0")) + parse_int(value_2))


def add_count_pair_sum(stats: Dict[str, str], key_base: str, value_1: str, value_2: str) -> None:
    first = parse_count_pair(value_1)
    second = parse_count_pair(value_2)
    stats[f"{key_base}_landed_1"] = str(parse_int(stats.get(f"{key_base}_landed_1", "0")) + parse_int(first["made"]))
    stats[f"{key_base}_att_1"] = str(parse_int(stats.get(f"{key_base}_att_1", "0")) + parse_int(first["attempts"]))
    stats[f"{key_base}_landed_2"] = str(parse_int(stats.get(f"{key_base}_landed_2", "0")) + parse_int(second["made"]))
    stats[f"{key_base}_att_2"] = str(parse_int(stats.get(f"{key_base}_att_2", "0")) + parse_int(second["attempts"]))


def add_landed_sum(stats: Dict[str, str], key_base: str, value_1: str, value_2: str) -> None:
    first = parse_count_pair(value_1)
    second = parse_count_pair(value_2)
    stats[f"{key_base}_1"] = str(parse_int(stats.get(f"{key_base}_1", "0")) + parse_int(first["made"]))
    stats[f"{key_base}_2"] = str(parse_int(stats.get(f"{key_base}_2", "0")) + parse_int(second["made"]))


def add_time_sum(stats: Dict[str, str], key_base: str, value_1: str, value_2: str) -> None:
    first = parse_time_seconds(value_1)
    second = parse_time_seconds(value_2)
    stats[f"{key_base}_1"] = str(parse_int(stats.get(f"{key_base}_1", "0")) + parse_int(first))
    stats[f"{key_base}_2"] = str(parse_int(stats.get(f"{key_base}_2", "0")) + parse_int(second))


def parse_stats_tables(soup: BeautifulSoup) -> Dict[str, str]:
    stats: Dict[str, str] = {}
    tables = soup.select("table.b-fight-details__table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [normalize_header(cell.get_text()) for cell in rows[0].find_all(["td", "th"])]
        if not headers or headers[0] != "fighter":
            continue
        for row in rows[1:]:
            cells = [normalize_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["td", "th"])]
            if len(cells) != len(headers):
                continue
            for i in range(1, len(headers)):
                header = headers[i]
                value_1, value_2 = split_dual_values(cells[i])
                if header == "kd":
                    add_sum(stats, "knockdowns", value_1, value_2)
                elif header == "sig str":
                    add_count_pair_sum(stats, "significant_strikes", value_1, value_2)
                elif header == "sig str %":
                    # Ignore per-round percentages; compute overall accuracy from totals.
                    pass
                elif header == "total str":
                    add_count_pair_sum(stats, "total_strikes", value_1, value_2)
                elif header == "td":
                    first = parse_count_pair(value_1)
                    second = parse_count_pair(value_2)
                    stats["takedowns_succ_1"] = str(parse_int(stats.get("takedowns_succ_1", "0")) + parse_int(first["made"]))
                    stats["takedowns_att_1"] = str(parse_int(stats.get("takedowns_att_1", "0")) + parse_int(first["attempts"]))
                    stats["takedowns_succ_2"] = str(parse_int(stats.get("takedowns_succ_2", "0")) + parse_int(second["made"]))
                    stats["takedowns_att_2"] = str(parse_int(stats.get("takedowns_att_2", "0")) + parse_int(second["attempts"]))
                elif header == "td %":
                    # Some pages write the takedown counts under a duplicated header.
                    if " of " in value_1 or " of " in value_2:
                        first = parse_count_pair(value_1)
                        second = parse_count_pair(value_2)
                        stats["takedowns_succ_1"] = str(parse_int(stats.get("takedowns_succ_1", "0")) + parse_int(first["made"]))
                        stats["takedowns_att_1"] = str(parse_int(stats.get("takedowns_att_1", "0")) + parse_int(first["attempts"]))
                        stats["takedowns_succ_2"] = str(parse_int(stats.get("takedowns_succ_2", "0")) + parse_int(second["made"]))
                        stats["takedowns_att_2"] = str(parse_int(stats.get("takedowns_att_2", "0")) + parse_int(second["attempts"]))
                    else:
                        pass
                elif header == "sub att":
                    add_sum(stats, "subs_att", value_1, value_2)
                elif header == "rev":
                    add_sum(stats, "reversals", value_1, value_2)
                elif header == "ctrl":
                    add_time_sum(stats, "control_time_seconds", value_1, value_2)
                elif header == "head":
                    add_landed_sum(stats, "sig_strikes_head", value_1, value_2)
                elif header == "body":
                    add_landed_sum(stats, "sig_strikes_body", value_1, value_2)
                elif header == "leg":
                    add_landed_sum(stats, "sig_strikes_leg", value_1, value_2)
                elif header == "distance":
                    add_landed_sum(stats, "distance_strikes", value_1, value_2)
                elif header == "clinch":
                    add_landed_sum(stats, "clinch_strikes", value_1, value_2)
                elif header == "ground":
                    add_landed_sum(stats, "ground_strikes", value_1, value_2)
    # Recompute takedown and significant strike totals from summed values
    if stats.get("takedowns_att_1"):
        att1 = parse_int(stats["takedowns_att_1"])
        if att1 > 0:
            stats["takedowns_pct_1"] = str(round(parse_int(stats["takedowns_succ_1"]) * 100 / att1))
        else:
            stats["takedowns_pct_1"] = "0"
    if stats.get("takedowns_att_2"):
        att2 = parse_int(stats["takedowns_att_2"])
        if att2 > 0:
            stats["takedowns_pct_2"] = str(round(parse_int(stats["takedowns_succ_2"]) * 100 / att2))
        else:
            stats["takedowns_pct_2"] = "0"
    if stats.get("significant_strikes_att_1"):
        att1 = parse_int(stats["significant_strikes_att_1"])
        if att1 > 0:
            stats["sig_strikes_accuracy_1"] = str(round(parse_int(stats["significant_strikes_landed_1"]) * 100 / att1))
        else:
            stats["sig_strikes_accuracy_1"] = "0"
    if stats.get("significant_strikes_att_2"):
        att2 = parse_int(stats["significant_strikes_att_2"])
        if att2 > 0:
            stats["sig_strikes_accuracy_2"] = str(round(parse_int(stats["significant_strikes_landed_2"]) * 100 / att2))
        else:
            stats["sig_strikes_accuracy_2"] = "0"
    # Compute defenses
    if stats.get("significant_strikes_att_2"):
        att2 = parse_int(stats["significant_strikes_att_2"])
        if att2 > 0:
            defense_1 = round((att2 - parse_int(stats.get("significant_strikes_landed_2", "0"))) * 100 / att2)
            stats["sig_strikes_defense_1"] = str(defense_1)
        else:
            stats["sig_strikes_defense_1"] = "0"
    if stats.get("significant_strikes_att_1"):
        att1 = parse_int(stats["significant_strikes_att_1"])
        if att1 > 0:
            defense_2 = round((att1 - parse_int(stats.get("significant_strikes_landed_1", "0"))) * 100 / att1)
            stats["sig_strikes_defense_2"] = str(defense_2)
        else:
            stats["sig_strikes_defense_2"] = "0"
    if stats.get("takedowns_att_2"):
        att2 = parse_int(stats["takedowns_att_2"])
        if att2 > 0:
            td_defense_1 = round((att2 - parse_int(stats.get("takedowns_succ_2", "0"))) * 100 / att2)
            stats["takedowns_defense_1"] = str(td_defense_1)
        else:
            stats["takedowns_defense_1"] = "0"
    if stats.get("takedowns_att_1"):
        att1 = parse_int(stats["takedowns_att_1"])
        if att1 > 0:
            td_defense_2 = round((att1 - parse_int(stats.get("takedowns_succ_1", "0"))) * 100 / att1)
            stats["takedowns_defense_2"] = str(td_defense_2)
        else:
            stats["takedowns_defense_2"] = "0"
    return stats


def extract_fighter_names(soup: BeautifulSoup) -> List[str]:
    names = []
    for selector in [".b-fight-details__person-name", "a.b-link.b-fight-details__person-link"]:
        for node in soup.select(selector):
            text = normalize_text(node.get_text(" ", strip=True))
            if text and text not in names:
                names.append(text)
            if len(names) == 2:
                return names
    return names


def extract_winner(soup: BeautifulSoup) -> str:
    statuses = {}
    for person in soup.select("div.b-fight-details__person"):
        name_node = person.select_one(".b-fight-details__person-name")
        if not name_node:
            continue
        name = normalize_text(name_node.get_text(strip=True))
        status_icon = person.select_one(".b-fight-details__person-status")
        if status_icon:
            status_text = normalize_text(status_icon.get_text(strip=True)).upper()
            statuses[name] = status_text

    # If one fighter has W, they are the winner
    for name, status in statuses.items():
        if status == "W":
            return name

    # If both have D, it's a draw
    if all(s == "D" for s in statuses.values()) and len(statuses) == 2:
        return "Draw"

    # If one has L, the other is the winner
    for name, status in statuses.items():
        if status == "L":
            others = [n for n in statuses if n != name]
            if others:
                return others[0]

    return ""


def parse_event_list(session: requests.Session) -> List[Dict[str, str]]:
    response = safe_get(EVENTS_URL, session)
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table", class_=lambda value: value and "statistics__table-events" in value)
    if table is None:
        table = soup.find("table")
    if table is None:
        raise RuntimeError("No events table found on UFC Stats event listing page.")

    rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
    events: List[Dict[str, str]] = []
    for row in rows:
        link = row.find("a", href=True)
        if link is None:
            continue
        event_url = link["href"].strip()
        if event_url.startswith("/"):
            event_url = BASE_URL + event_url
        if "/event-details/" not in event_url:
            continue
        cells = [normalize_text(td.get_text(" ", strip=True)) for td in row.find_all("td")]
        event_name = normalize_text(link.get_text(strip=True))
        event_location = cells[1] if len(cells) > 1 else ""
        full_text = normalize_text(cells[0]) if cells else ""
        event_date = full_text.replace(event_name, "").strip()
        events.append(
            {
                "event_name": event_name,
                "event_date": event_date,
                "event_location": event_location,
                "event_url": event_url,
            }
        )
    return events


def parse_event_page(session: requests.Session, event: Dict[str, str]) -> List[Dict[str, str]]:
    response = safe_get(event["event_url"], session)
    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select("table.b-fight-details__table tbody tr")
    if not rows:
        rows = soup.select("table tbody tr")
    if not rows:
        raise RuntimeError(f"Could not find fights table for event {event['event_url']}")

    fights: List[Dict[str, str]] = []
    seen_urls = set()
    for row in rows:
        fight_link = row.find("a", href=True)
        if fight_link is None:
            continue
        fight_url = fight_link["href"].strip()
        if fight_url.startswith("/"):
            fight_url = BASE_URL + fight_url
        if "/fight-details/" not in fight_url:
            continue
        if fight_url in seen_urls:
            continue
        seen_urls.add(fight_url)

        cells = [normalize_text(td.get_text(" ", strip=True)) for td in row.find_all("td")]
        fighter_cell = row.find_all("td")[1] if len(row.find_all("td")) > 1 else None
        fighter_names = []
        if fighter_cell:
            for a in fighter_cell.find_all("a", href=True):
                name = normalize_text(a.get_text(strip=True))
                if name:
                    fighter_names.append(name)
        fighter_1 = fighter_names[0] if len(fighter_names) > 0 else ""
        fighter_2 = fighter_names[1] if len(fighter_names) > 1 else ""

        weight_class = cells[6] if len(cells) > 6 else ""
        method = cells[7] if len(cells) > 7 else ""
        round_ = cells[8] if len(cells) > 8 else ""
        fight_time = cells[9] if len(cells) > 9 else ""

        fights.append(
            {
                "fight_url": fight_url,
                "weight_class": weight_class,
                "method": method,
                "round": round_,
                "time": fight_time,
                "fighter_1": fighter_1,
                "fighter_2": fighter_2,
            }
        )
    return fights


def parse_fight_detail(session: requests.Session, fight: Dict[str, str]) -> Dict[str, str]:
    response = safe_get(fight["fight_url"], session)
    soup = BeautifulSoup(response.text, "html.parser")

    names = extract_fighter_names(soup)
    fighter_1 = names[0] if len(names) > 0 else fight.get("fighter_1", "")
    fighter_2 = names[1] if len(names) > 1 else fight.get("fighter_2", "")
    winner = extract_winner(soup)
    stats = parse_stats_tables(soup)

    # Extract scheduled rounds from Time format field
    scheduled_rounds = ""
    for p in soup.select("p.b-fight-details__text"):
        text = normalize_text(p.get_text(" ", strip=True))
        if "Time format:" in text:
            match = re.search(r"(\d+)\s*Rnd", text)
            if match:
                scheduled_rounds = match.group(1)
            break

    result: Dict[str, str] = {
        "fighter_1": fighter_1,
        "fighter_2": fighter_2,
        "winner": winner,
        "scheduled_rounds": scheduled_rounds,
    }
    result.update(stats)
    return result


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


def fight_has_stats(row: Dict[str, str]) -> bool:
    required_columns = [
        "knockdowns_1",
        "total_strikes_landed_1",
        "significant_strikes_landed_1",
        "sig_strikes_head_1",
        "takedowns_att_1",
        "control_time_seconds_1",
        "subs_att_1",
    ]
    return any(str(row.get(column, "")).strip() for column in required_columns)


def build_record(event: Dict[str, str], fight: Dict[str, str], detail: Dict[str, str]) -> Dict[str, str]:
    record = {key: "" for key in COLUMNS}
    record.update(
        {
            "event_date": event.get("event_date", ""),
            "event_name": event.get("event_name", ""),
            "event_location": event.get("event_location", ""),
            "event_url": event.get("event_url", ""),
            "fight_url": fight.get("fight_url", ""),
            "weight_class": fight.get("weight_class", ""),
            "method": fight.get("method", ""),
            "round": fight.get("round", ""),
            "time": fight.get("time", ""),
            "fighter_1": detail.get("fighter_1", fight.get("fighter_1", "")),
            "fighter_2": detail.get("fighter_2", fight.get("fighter_2", "")),
            "winner": detail.get("winner", ""),
        }
    )
    for key, value in detail.items():
        if key in record:
            record[key] = value
    return record


def main() -> None:
    print("Starting UFC scraper. Output file:", OUTPUT_FILE)
    session = create_session()
    existing_df = load_existing_data()
    rows_by_fight: Dict[str, Dict[str, str]] = {
        row["fight_url"]: row
        for row in existing_df.to_dict(orient="records")
        if row.get("fight_url")
    }

    events = parse_event_list(session)
    print(f"Found {len(events)} completed events.")

    for index, event in enumerate(events, start=1):
        print(f"\n[{index}/{len(events)}] Event: {event['event_name']} - {event['event_date']} ({event['event_location']})")

        try:
            fights = parse_event_page(session, event)
        except Exception as exc:
            print(f"[ERROR] Unable to parse event page: {exc}")
            continue

        pending_fights = []
        for fight in fights:
            existing = rows_by_fight.get(fight["fight_url"])
            if existing is None:
                pending_fights.append((fight, "new"))
            elif not fight_has_stats(existing):
                pending_fights.append((fight, "update"))

        if not pending_fights:
            print("  > All fights for this event are already complete. Skipping event.")
            continue

        print(f"  > Found {len(fights)} fights, {len(pending_fights)} pending to update or add.")
        for fight_index, (fight, mode) in enumerate(pending_fights, start=1):
            print(f"    - [{mode}] Fight {fight_index}/{len(pending_fights)}: {fight.get('fighter_1','?')} vs {fight.get('fighter_2','?')}")
            try:
                detail = parse_fight_detail(session, fight)
            except Exception as exc:
                print(f"      [ERROR] Failed to parse fight {fight['fight_url']}: {exc}")
                continue

            record = build_record(event, fight, detail)
            rows_by_fight[fight["fight_url"]] = record
            save_data(pd.DataFrame(list(rows_by_fight.values()), columns=COLUMNS))
            print("      Saved.")
            time.sleep(random.uniform(1.0, 2.5))

    final_rows = list(rows_by_fight.values())
    if final_rows:
        save_data(pd.DataFrame(final_rows, columns=COLUMNS))
        print(f"\nScraping completed. Final output saved to {OUTPUT_FILE}")
    else:
        print("\nNo rows were generated.")


if __name__ == "__main__":
    main()