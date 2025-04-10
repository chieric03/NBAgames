import os
import pandas as pd
from bs4 import BeautifulSoup

def parse_html(box_score):
    with open(box_score) as f:
        html = f.read()

    #cleaning html
    soup = BeautifulSoup(html)
    [s.decompose() for s in soup.select("tr.over_header")]
    [s.decompose() for s in soup.select("tr.thead")]
    return soup

def read_linescore(soup):
    line_score = pd.read_html(str(soup), attrs = {"id": "line_score"} )[0]
    cols = list(line_score.columns)
    cols[0] = "team"
    cols[-1] = "total"
    line_score.columns = cols
    line_score = line_score[["team", "total"]]
    return line_score

def read_stats(soup, team, stat_type):
    df = pd.read_html(str(soup), attrs = {"id": f'box-{team}-game-{stat_type}'}, index_col = 0)[0]
    df = df.apply(pd.to_numeric, errors = "coerce") #converts string stats to NaN
    return df

def read_season_info(soup):
    nav = soup.select("#bottom_nav_container")[0]
    hrefs = [a["href"] for a in nav.find_all("a")]
    season = os.path.basename(hrefs[1]).split("_")[0]
    return season
