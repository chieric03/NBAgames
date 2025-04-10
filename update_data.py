import os
import pandas as pd
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import time
import sqlite3
import asyncio
from datetime import datetime, timedelta
import re # For parsing month from URL

# --- Constants ---
DATA_DIR = 'data'
MONTHS_DIR = os.path.join(DATA_DIR, 'months')
SCORES_DIR = os.path.join(DATA_DIR, 'scores')
DB_FILE = "nba_data.db"
TABLE_NAME = "games"
DEFAULT_START_DATE = "2017-10-01" # Start of 2018 season
BASE_URL = "https://www.basketball-reference.com"

# --- Scraping Functions ---
async def get_html(url, selector, sleep=3, retries=3):
    """ Fetches HTML using Playwright with retries and backoff. """
    html = None
    for i in range(1, retries + 1):
        time.sleep(sleep * (i / 2))
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"})
                await page.goto(url, timeout=90000)
                print(f"Attempting to fetch: {url} (Attempt {i}/{retries})")
                page_title = await page.title()
                # print(f"Page title: {page_title}") # Reduce verbosity
                await page.wait_for_selector(selector, timeout=45000)
                html = await page.inner_html(selector, timeout=45000)
                await browser.close()
        except PlaywrightTimeout:
            print(f"Timeout error on {url} (Attempt {i}/{retries})")
            continue
        except Exception as e:
            print(f"Error fetching {url} (Attempt {i}/{retries}): {e}")
            continue
        else:
            # print(f"Successfully fetched: {url}") # Reduce verbosity
            break
    return html

async def scrape_schedule_month(url):
    """ Scrapes monthly schedule page HTML. """
    month_filename = url.split('/')[-1]
    save_path = os.path.join(MONTHS_DIR, month_filename)
    if os.path.exists(save_path): return save_path
    print(f"Scraping month schedule: {url}")
    html = await get_html(url, '#all_schedule')
    if html:
        os.makedirs(MONTHS_DIR, exist_ok=True)
        with open(save_path, 'w+', encoding='utf-8') as f: f.write(html)
        print(f"Saved month schedule: {save_path}")
        return save_path
    else:
        print(f"Failed to fetch month schedule: {url}")
        return None

async def scrape_game_boxscore(url):
    """ Scrapes individual game box score HTML. """
    boxscore_filename = url.split('/')[-1]
    save_path = os.path.join(SCORES_DIR, boxscore_filename)
    if os.path.exists(save_path): return save_path
    # print(f"Scraping box score: {url}") # Reduce verbosity
    html = await get_html(url, '#content')
    if html:
        os.makedirs(SCORES_DIR, exist_ok=True)
        with open(save_path, 'w+', encoding='utf-8') as f: f.write(html)
        # print(f"Saved box score: {save_path}") # Reduce verbosity
        return save_path
    else:
        print(f"Failed to fetch box score: {url}")
        return None

# --- Parsing Functions ---
def parse_html(box_score_path):
    try:
        with open(box_score_path, 'r', encoding='utf-8') as f: html = f.read()
        soup = BeautifulSoup(html, 'lxml')
        [s.decompose() for s in soup.select("tr.over_header")]
        [s.decompose() for s in soup.select("tr.thead")]
        return soup
    except Exception as e:
        print(f"Error parsing HTML file {box_score_path}: {e}")
        return None

def read_linescore(soup):
    if soup is None: return None
    try:
        dfs = pd.read_html(str(soup), attrs={"id": "line_score"})
        if not dfs: return None
        line_score = dfs[0].copy() # Use copy to avoid SettingWithCopyWarning
        cols = list(line_score.columns)
        cols[0] = "team"
        cols[-1] = "total"
        line_score.columns = cols
        line_score = line_score[["team", "total"]]
        return line_score
    except Exception as e: return None

def read_stats(soup, team, stat_type):
    if soup is None: return None
    try:
        dfs = pd.read_html(str(soup), attrs={"id": f'box-{team}-game-{stat_type}'}, index_col=0)
        if not dfs: return None
        df = dfs[0].copy()
        df = df.apply(pd.to_numeric, errors="coerce")
        return df
    except ValueError: return None
    except Exception: return None

def read_season_info(soup):
    if soup is None: return None
    try:
        nav = soup.select("#bottom_nav_container")[0]
        hrefs = [a["href"] for a in nav.find_all("a")]
        season = os.path.basename(hrefs[1]).split("_")[0]
        return season
    except Exception: return None

# --- Helper Function ---
def get_month_from_url(url):
    """ Extracts month (YYYY-MM) from basketball-reference month URL """
    month_map = { 'october': 10, 'november': 11, 'december': 12, 'january': 1,
                  'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
                  'july': 7, 'august': 8, 'september': 9 }
    match = re.search(r"_games-([a-z]+)(?:-\d{4})?\.html", url)
    if match:
        month_name = match.group(1)
        season_match = re.search(r"/leagues/NBA_(\d{4})_games", url)
        if season_match:
            season_year = int(season_match.group(1))
            month_num = month_map.get(month_name)
            if month_num is None: return None
            year = season_year - 1 if month_num >= 10 else season_year
            try:
                return pd.Timestamp(f"{year}-{month_num:02d}-01") # Ensure 2-digit month
            except ValueError: # Handle invalid date combinations if any
                return None
    return None

# --- Main Update Logic ---
async def main():
    # Ensure data directories exist
    os.makedirs(MONTHS_DIR, exist_ok=True)
    os.makedirs(SCORES_DIR, exist_ok=True)

    # 0. Get set of already existing score files (before scraping)
    try:
        existing_score_files = set(os.listdir(SCORES_DIR))
        print(f"Found {len(existing_score_files)} box score files before scraping.")
    except FileNotFoundError:
        existing_score_files = set()
        print("Scores directory not found initially.")


    # 1. Determine Date Range for Scraping
    start_date_dt = None
    end_date_dt = datetime.now() - timedelta(days=1) # Yesterday
    db_exists = os.path.exists(DB_FILE)
    table_exists = False

    if db_exists:
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{TABLE_NAME}';")
            table_exists = cursor.fetchone() is not None
            if table_exists:
                max_date_str = cursor.execute(f"SELECT MAX(date) FROM {TABLE_NAME}").fetchone()[0]
                if max_date_str:
                    start_date_dt = pd.to_datetime(max_date_str) - timedelta(days=1)
                    print(f"Last date in DB: {max_date_str}. Starting check from {start_date_dt.strftime('%Y-%m-%d')}")
            conn.close()
        except Exception as e:
            print(f"Error reading max date from DB: {e}. Using default start date.")

    if start_date_dt is None:
        start_date_dt = pd.to_datetime(DEFAULT_START_DATE)
        print(f"No existing data found or error reading DB. Starting check from default: {DEFAULT_START_DATE}")

    # 2. Efficient Scraping (Fetch relevant months, then scrape games sequentially)
    print(f"\n--- Scraping Phase (Checking from {start_date_dt.strftime('%Y-%m-%d')} to {end_date_dt.strftime('%Y-%m-%d')}) ---")
    start_season = start_date_dt.year + 1 if start_date_dt.month >= 10 else start_date_dt.year
    end_season = end_date_dt.year + 1 if end_date_dt.month >= 10 else end_date_dt.year

    all_monthly_schedule_urls = []
    # Fetch month links only for relevant seasons
    for season_year in range(start_season, end_season + 1):
        season_schedule_url = f"{BASE_URL}/leagues/NBA_{season_year}_games.html"
        print(f"Fetching valid months for season {season_year}...")
        filter_html = await get_html(season_schedule_url, '#content .filter')
        if filter_html:
            soup = BeautifulSoup(filter_html, 'lxml')
            links = soup.find_all('a')
            for link in links:
                href = link.get('href')
                if href and f"/leagues/NBA_{season_year}_games-" in href:
                    all_monthly_schedule_urls.append(f"{BASE_URL}{href}")
        else: print(f"Could not fetch month list for season {season_year}")

    # Filter month URLs by date range
    relevant_month_urls = []
    for url in all_monthly_schedule_urls:
         month_start_dt = get_month_from_url(url)
         if month_start_dt:
             month_end_dt = month_start_dt + pd.offsets.MonthEnd(0)
             if month_start_dt <= end_date_dt and month_end_dt >= start_date_dt:
                 relevant_month_urls.append(url)

    print(f"Filtered down to {len(relevant_month_urls)} relevant monthly schedule pages.")

    # Scrape relevant months and games sequentially
    newly_downloaded_files = []
    for month_url in relevant_month_urls:
        month_file_path = await scrape_schedule_month(month_url)
        if month_file_path and os.path.exists(month_file_path):
            with open(month_file_path, 'r', encoding='utf-8') as f: html = f.read()
            soup = BeautifulSoup(html, 'lxml')
            links = soup.find_all('a')
            hrefs = [l.get('href') for l in links]
            box_scores_links = [l for l in hrefs if l and 'boxscores' in l and '.html' in l]
            box_scores_urls = [f'{BASE_URL}{l}' for l in box_scores_links]

            print(f"Checking {len(box_scores_urls)} box scores for month {os.path.basename(month_url)}...")
            for game_url in box_scores_urls:
                 try:
                     game_date_str = os.path.basename(game_url)[:8]
                     game_date_dt = pd.to_datetime(game_date_str, format="%Y%m%d")
                     if start_date_dt <= game_date_dt <= end_date_dt:
                         # Check if file existed *before* this run
                         fname = os.path.basename(game_url)
                         existed_before = fname in existing_score_files
                         # Scrape (will skip download if file exists)
                         scraped_path = await scrape_game_boxscore(game_url)
                         # If scrape was successful AND the file didn't exist before, mark as new
                         if scraped_path and not existed_before:
                             newly_downloaded_files.append(scraped_path)
                 except Exception as e:
                     print(f"Error processing game URL {game_url}: {e}")

    print(f"\n--- Scraping Phase Complete --- Found {len(newly_downloaded_files)} newly downloaded box score files.")

    # 3. Parse ONLY NEW Files
    print("\n--- Parsing Phase (Incremental) ---")
    if not newly_downloaded_files:
        print("No new box score files to parse.")
        games_to_append = []
    else:
        print(f"Parsing {len(newly_downloaded_files)} new HTML box score files...")
        base_cols = None # Reset base_cols for safety, though should be consistent
        games_to_append = []
        processed_count = 0
        skipped_count = 0

        for box_score_path in newly_downloaded_files:
            soup = parse_html(box_score_path)
            if soup is None: skipped_count += 1; continue
            line_score = read_linescore(soup)
            if line_score is None: skipped_count += 1; continue
            teams = list(line_score["team"])
            if len(teams) != 2: skipped_count += 1; continue

            summaries = []
            skip_game = False
            for team in teams:
                basic = read_stats(soup, team, "basic")
                advanced = read_stats(soup, team, "advanced")
                if basic is None or advanced is None: skip_game = True; break
                if "Team Totals" not in basic.index or "Team Totals" not in advanced.index: skip_game = True; break

                totals = pd.concat([basic.loc["Team Totals"], advanced.loc["Team Totals"]])
                maxes = pd.concat([basic.drop("Team Totals").max(), advanced.drop("Team Totals").max()])
                maxes.index = maxes.index.str.lower() + "_max"
                totals.index = totals.index.str.lower()
                summary = pd.concat([totals, maxes])

                # Define base_cols based on the first successfully parsed game if not set
                if base_cols is None:
                    base_cols = list(summary.index.drop_duplicates(keep="first"))
                    base_cols = [b for b in base_cols if "bpm" not in b]

                summary = summary.reindex(base_cols)
                summaries.append(summary)

            if skip_game: skipped_count += 1; continue

            try:
                summary_df = pd.concat(summaries, axis=1).T
                game = pd.concat([summary_df, line_score.set_index('team')], axis=1)
            except Exception as e: skipped_count += 1; continue

            game["home"] = [0, 1]
            game_opp = game.iloc[::-1].reset_index(drop=True)
            game_opp.columns += "_opp"
            full_game = pd.concat([game.reset_index(), game_opp], axis=1)

            season = read_season_info(soup)
            if season is None: skipped_count += 1; continue
            full_game["season"] = season

            try:
                game_date_str = os.path.basename(box_score_path)[:8]
                full_game["date"] = pd.to_datetime(game_date_str, format="%Y%m%d")
            except ValueError: skipped_count += 1; continue

            if "total" not in full_game.columns or "total_opp" not in full_game.columns: skipped_count += 1; continue
            full_game["winner"] = full_game["total"] > full_game["total_opp"]

            games_to_append.append(full_game)
            processed_count += 1
            if processed_count % 100 == 0: # Print less often for append
                print(f"Parsed {processed_count} new games...")

        print(f"Finished parsing new files. Processed: {processed_count}, Skipped: {skipped_count}")

    # 4. Append to Database
    if games_to_append:
        new_games_df = pd.concat(games_to_append, ignore_index=True)
        print(f"\nConcatenated {len(new_games_df)} new rows for database.")

        # Clean column names
        new_games_df.columns = new_games_df.columns.str.replace('%', '_percent', regex=False)
        new_games_df.columns = new_games_df.columns.str.replace('+/-', 'plus_minus', regex=False)
        new_games_df.columns = new_games_df.columns.str.replace('3p', 'fg3p', regex=False)
        new_games_df.columns = [f"{c}_team" if c == "mp_max" else c for c in new_games_df.columns]
        new_games_df.columns = [c.replace('_max_opp', '_opp_max') if c.endswith('_max_opp') else c for c in new_games_df.columns]

        try:
            conn = sqlite3.connect(DB_FILE)
            print(f"Appending data to table '{TABLE_NAME}' in {DB_FILE}...")
            # Use if_exists='append'
            new_games_df.to_sql(TABLE_NAME, conn, if_exists='append', index=False)
            print("Data appended successfully.")

            # Create indexes only if the table didn't exist before this run
            if not table_exists:
                print("Creating indexes on 'team' and 'date' columns...")
                cursor = conn.cursor()
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_team ON {TABLE_NAME} (team);")
                cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_date ON {TABLE_NAME} (date);")
                conn.commit()
                print("Indexes created successfully.")
            else:
                print("Indexes should already exist.")

        except Exception as e:
            print(f"Error interacting with database: {e}")
        finally:
            if conn:
                conn.close()
                print("Database connection closed.")
    else:
        print("\nNo new games parsed, database not updated.")

if __name__ == "__main__":
    asyncio.run(main())
