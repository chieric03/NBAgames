import os
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import time

DATA_DIR = 'data'
MONTHS_DIR = os.path.join(DATA_DIR, "months")
SCORES_DIR = os.path.join(DATA_DIR, "scores")

async def get_html(url, selector, sleep=3, retries = 3):
    """
    Fetches the HTML content of a specified element from a webpage using Playwright.
    Args:
        url (str): The URL of the webpage to fetch the HTML from.
        selector (str): The CSS selector of the element to fetch the HTML content from.
        sleep (int, optional): The base number of seconds to wait between retries. Defaults to 5.
        retries (int, optional): The number of times to retry fetching the HTML in case of failure. Defaults to 3.
    Returns:
        str: The HTML content of the specified element, or None if the fetch fails after the specified retries.
    Raises:
        PlaywrightTimeout: If the request times out.
    """

    html = None
    for i in range(1,retries+1):
        time.sleep(sleep * i) #makes sure we dont scrape too fast and we dont get banned.

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.goto(url)
                print(await page.title())
                html = await page.inner_html(selector)
        except PlaywrightTimeout:
            print(f"Timeout on {url}")
            continue
        else: 
            break
    return html


async def scrape_season(season):
    url = f"https://www.basketball-reference.com/leagues/NBA_{season}_games.html"
    html = await get_html(url, '#content .filter')
    soup = BeautifulSoup(html)
    links = soup.find_all('a')
    href = [l['href'] for l in links]
    months_pages = [f'https://www.basketball-reference.com{l}' for l in href]

    for url in months_pages:
        save_path = os.path.join(MONTHS_DIR, url.split('/')[-1]) #naming by month
        if os.path.exists(save_path):
            print(f"Skipping {url}")
            continue

        html = await get_html(url, '#all_schedule')
        with open(save_path, 'w+') as f:
            f.write(html)

async def scrape_game(months_file):
    """
    Scrapes game data from a given HTML file containing links to box scores.

    Args:
        months_file (str): The path to the HTML file containing links to box scores.

    Returns:
        None

    This function reads the HTML content from the specified file, extracts links to box scores,
    and then scrapes the box score data from each link. The scraped data is saved to a specified
    directory. If the data for a particular box score already exists, it skips that box score.
    """
    with open(months_file, 'r') as f:
        html = f.read()

    soup = BeautifulSoup(html)
    links = soup.find_all('a')
    hrefs = [l.get('href') for l in links]
    box_scores = [l for l in hrefs if l and 'boxscore' in l and '.html' in l]
    #box_scores is jut the ending hmtl path, we need to add the base
    box_scores = [f'https://www.basketball-reference.com{l}' for l in box_scores]

    #Now we have the urls, we can scrape the box scores.
    for url in box_scores:
        save_path = os.path.join(SCORES_DIR, url.split('/')[-1])
        if os.path.exists(save_path):
            print(f"Skipping {url}")
            continue
        html = await get_html(url, '#content')
        if not html:
            continue
        with open(save_path, 'w+') as f:
            f.write(html)
        print(f"Saved {url}")
