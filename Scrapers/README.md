# Scrapers

This folder contains all the scripts used to collect and clean the data for the UFC Fight Analysis project.

All data is scraped from [ufcstats.com](http://ufcstats.com) or [Wikipedia](https://en.wikipedia.org/wiki/List_of_UFC_champions) or downloaded from Kaggle. The output is a set of CSV files stored in the `Data/` folder.

## Prerequisites

Python 3.10+ is required. Install all dependencies with:

```bash
pip install requests beautifulsoup4 pandas
```

## Scrapers

### ufc_scraper.py
Scrapes all completed UFC events and fights from ufcstats.com. For each fight it extracts detailed statistics including strikes, takedowns, control time, knockdowns and finish method.

- **Input:** ufcstats.com (live)
- **Output:** `Data/ufc_fights.csv`
- **Run:** `python ufc_scraper.py`

The scraper is incremental — if interrupted, it resumes from where it left off without re-scraping completed fights.

### scrape_fighter_urls.py
Collects the profile URLs of all fighters listed on ufcstats.com, going through the alphabet from A to Z.

- **Input:** ufcstats.com (live)
- **Output:** `Data/ufc_fighter_urls.csv`
- **Run:** `python scrape_fighter_urls.py`

Must be run before `scrape_fighter_data.py`.

### scrape_fighter_data.py
Scrapes the profile page of each fighter URL collected by `scrape_fighter_urls.py`. Extracts physical attributes, fight record and career statistics.

- **Input:** `Data/ufc_fighter_urls.csv`
- **Output:** `Data/ufc_fighters.csv`
- **Run:** `python scrape_fighter_data.py`

Incremental — skips fighters already scraped.

### scrape_champions.py
Scrapes the full UFC championship history from Wikipedia, covering all weight divisions. For each champion it visits their individual Wikipedia page to extract accurate title defense counts per division.

- **Input:** Wikipedia (live)
- **Output:** `Data/ufc_champions.csv`
- **Run:** `python scrape_champions.py`

Note: this script is slower than the others (~10 minutes) due to rate limiting on Wikipedia requests. If some champions show incorrect defense counts, run the script again — Wikipedia may block individual requests with a 403 error. Multiple runs are sometimes needed to fill all records correctly.

### data_cleaning.py
Cleans and standardizes all CSV files in the `Data/` folder. Removes invalid values, fixes swapped columns from older scraper versions, converts units and standardizes formats.

- **Input:** `Data/ufc_fights.csv`, `Data/ufc_fighters.csv`
- **Output:** Same files, cleaned in place
- **Run:** `python data_cleaning.py`

Safe to run multiple times — detects and fixes issues automatically without affecting correct data.

## Data files

### ufc_fights.csv
One row per fight. Contains fight-level statistics for all UFC events.

| Column | Description |
|---|---|
| event_date | Date of the event |
| event_name | Name of the event |
| event_location | City, state and country |
| fight_url | ufcstats.com fight page URL |
| fighter_1 / fighter_2 | Fighter names |
| winner | Winner name or "Draw" |
| method | Finish method (e.g. KO/TKO Punches, SUB Rear Naked Choke, U-DEC) |
| round | Round the fight ended |
| time | Time within the round |
| weight_class | Weight division |
| knockdowns_1 / knockdowns_2 | Knockdowns per fighter |
| total_strikes_landed / att | Total strikes landed and attempted |
| significant_strikes_landed / att | Significant strikes landed and attempted |
| sig_strikes_head / body / leg | Significant strikes by target zone |
| distance / clinch / ground_strikes | Significant strikes by position |
| sig_strikes_accuracy / defense | Strike accuracy and defense percentage |
| takedowns_succ / att | Takedowns landed and attempted |
| takedowns_pct / defense | Takedown accuracy and defense percentage |
| control_time_seconds | Ground control time in seconds |
| subs_att | Submission attempts |
| reversals | Reversals |

### ufc_fighters.csv
One row per fighter. Contains physical attributes, fight record and career statistics.

| Column | Description |
|---|---|
| fighter_url | ufcstats.com fighter profile URL |
| fighter_name | Full name |
| nickname | Fighter nickname |
| height_cm | Height in centimetres |
| weight_lbs | Weight in pounds |
| reach_cm | Reach in centimetres |
| stance | Fighting stance (Orthodox, Southpaw, Switch) |
| date_of_birth | Date of birth (YYYY-MM-DD) |
| wins / losses / draws | Fight record |
| no_contests | No contest results |
| slpm | Significant strikes landed per minute |
| str_acc | Strike accuracy (0-1) |
| sapm | Significant strikes absorbed per minute |
| str_def | Strike defence (0-1) |
| td_avg | Takedowns per 15 minutes |
| td_acc | Takedown accuracy (0-1) |
| td_def | Takedown defence (0-1) |
| sub_avg | Submission attempts per 15 minutes |

### ufc_fighter_urls.csv
Reference file containing the ufcstats.com profile URL of every fighter. Used as input by `scrape_fighter_data.py`.

| Column | Description |
|---|---|
| fighter_url | ufcstats.com fighter profile URL |

### ufc_champions.csv
Full championship history for all UFC weight divisions, scraped from Wikipedia.

| Column | Description |
|---|---|
| division | Weight division name |
| reign_number | Number of the reign within the division |
| champion | Fighter name |
| defeated | Opponent defeated to win the title |
| event_won | Event where the title was won |
| date_won | Date the title was won |
| reign_days | Total days as champion |
| defenses_count |total title defenses in that division across all reigns |
| defense_details | Details of each defense (opponent, event, date) |

### UFC_betting_odds.csv
Betting odds for UFC fights from multiple bookmakers. Multiple rows per fight (one per bookmaker).

| Column | Description |
|---|---|
| fight_url | ufcstats.com fight URL — use to merge with ufc_fights.csv |
| fighter_1_url / fighter_2_url | ufcstats.com fighter profile URLs |
| fighter_1 / fighter_2 | Fighter names |
| odds_1 / odds_2 | Decimal odds per fighter |
| f1_ko_odds / f2_ko_odds | Odds for KO/TKO finish |
| f1_sub_odds / f2_sub_odds | Odds for submission finish |
| f1_dec_odds / f2_dec_odds | Odds for decision finish |
| event_date | Date of the event |
| source | Bookmaker name |
| region | Bookmaker region (us, uk, eu) |

**Source:** [UFC Betting Odds Daily Dataset](https://www.kaggle.com/datasets/jerzyszocik/ufc-betting-odds-daily-dataset) by jerzyszocik on Kaggle.

To merge with ufc_fights.csv, aggregate by fight_url first (average odds across bookmakers) then join on fight_url.

## Execution order

Run the scripts in this order to build the dataset from scratch:

```bash
# 1. Scrape all fights and statistics
python ufc_scraper.py

# 2. Collect fighter profile URLs
python scrape_fighter_urls.py

# 3. Scrape fighter data
python scrape_fighter_data.py

# 4. Scrape championship history
python scrape_champions.py

# 5. Clean all datasets
python data_cleaning.py
```

Steps 1-4 are incremental and can be interrupted and resumed at any time. Step 5 can be run at any point to clean the data.

## Data sources & credits

| Source | Data | URL |
|---|---|---|
| ufcstats.com | Fight statistics, fighter profiles | http://ufcstats.com |
| Wikipedia | UFC championship history | https://en.wikipedia.org/wiki/List_of_UFC_champions |
| Kaggle — jerzyszocik | Betting odds 2010–2027 | https://www.kaggle.com/datasets/jerzyszocik/ufc-betting-odds-daily-dataset |

ufcstats.com does not have a robots.txt file and the data collected is factual sports information used for educational and personal research purposes only.
