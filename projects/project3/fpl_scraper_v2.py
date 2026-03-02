import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException
)
from selenium.webdriver.common.keys import Keys

# ---------------------------
# SETUP
# ---------------------------
driver = webdriver.Firefox()
driver.get("https://fantasy.premierleague.com/statistics")
wait = WebDriverWait(driver, 20)

data = []

#fuck cookies
try:
    wait.until(
        EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
    ).click()
except TimeoutException:
    pass


def to_int(s: str) -> int:
    """Parse ints like '914' or '1,234' safely."""
    if s is None:
        return 0
    s = s.strip().replace(",", "")
    return int(s) if s.isdigit() else 0

def get_table_column_indexes():
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))

    ths = driver.find_elements(By.CSS_SELECTOR, "table thead th")
    headers = [th.text.strip().lower() for th in ths]

    if not headers:
        ths = driver.find_elements(By.CSS_SELECTOR, "table [role='columnheader']")
        headers = [th.text.strip().lower() for th in ths]

    def find_idx(possible_names):
        for i, h in enumerate(headers):
            for name in possible_names:
                if name in h:
                    return i
        return None

    minutes_idx = find_idx(["minutes", "mins"])

    return {
        "minutes_idx": minutes_idx,
        "headers": headers
    }

def close_player_modal():
    try:
        close_btn = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "[role='dialog'] button")
            )
        )
        driver.execute_script("arguments[0].click();", close_btn)
    except:

        driver.switch_to.active_element.send_keys(Keys.ESCAPE)

    wait.until(
        EC.invisibility_of_element_located((By.CSS_SELECTOR, "[role='dialog']"))
    )

def scrape_matches_from_modal(name, team, position):
    match_rows = wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "[role='dialog'] tr[role='row']")
        )
    )

    scraped = 0

    for row in match_rows:
        if scraped >= 20:
            break

        try:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) < 10:
                continue

            gw = cells[0].text.strip()
            if not gw:
                continue

            # Opponent & venue
            opponent_cell = cells[1]
            try:
                location_text = opponent_cell.find_elements(By.TAG_NAME, "span")[-1].text.strip()
                team_name, venue = [x.strip() for x in location_text.split(",", 1)]
                opponent = team_name
                home = venue.lower() == "home"
            except:
                opponent = opponent_cell.text.strip()
                home = None

            score = cells[2].text.strip()
            minutes = cells[5].text.strip()
            goals = cells[6].text.strip()
            assists = cells[7].text.strip()
            #shots = cells[6].text.strip()
            xG = cells[8].text.strip()
            xA = cells[9].text.strip()

            xGC = cells[13].text.strip() if len(cells) > 13 else ""
            CS = cells[11].text.strip() if len(cells) > 16 else ""
            BPS = cells[25].text.strip() if len(cells) > 17 else ""
            YC = cells[21].text.strip() if len(cells) > 18 else ""
            RC = cells[22].text.strip() if len(cells) > 19 else ""

            points = cells[3].text.strip()

            data.append({
                "name": name,
                "team": team,
                "position": position,
                "gw": gw,
                "opponent": opponent,
                "home": home,
                "minutes": minutes,
                "xG": xG,
                "xA": xA,
                #"shots": shots,
                "xGC": xGC,
                "CS": CS,
                "BPS": BPS,
                "YC": YC,
                "RC": RC,
                "points": points,
                "score": score,
                "goals": goals,
                "assists": assists
            })

            scraped += 1

        except StaleElementReferenceException:
            continue

def scrape_current_page(colinfo):
    minutes_idx = colinfo["minutes_idx"]

    rows = wait.until(
        EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, "table tr[role='row']")
        )
    )

    for i in range(len(rows)):

        # Re-fetch rows each loop to avoid stale elements
        rows = driver.find_elements(By.CSS_SELECTOR, "table tr[role='row']")
        row = rows[i]

        try:
            name = row.find_element(By.CSS_SELECTOR, "span.rfkqam4").text.strip()
            team = row.find_element(By.CSS_SELECTOR, "span.rfkqam3 span:nth-child(1)").text.strip()
            position = row.find_element(By.CSS_SELECTOR, "span.rfkqam3 span:nth-child(2)").text.strip()
        except NoSuchElementException:
            continue

        try:
            tds = row.find_elements(By.TAG_NAME, "td")
            if minutes_idx is None or minutes_idx >= len(tds):
                # If we couldn't detect the minutes column, do not skip.
                pass
            else:
                total_minutes = to_int(tds[minutes_idx].text)
                if total_minutes < 300:
                    continue
        except Exception:
            # If parsing fails for any reason, don't skip
            pass

        try:
            # Open modal
            btn = row.find_element(By.CSS_SELECTOR, "button.rfkqam1")
            driver.execute_script("arguments[0].click();", btn)

            wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "[role='dialog']"))
            )

            scrape_matches_from_modal(name, team, position)

        finally:
            close_player_modal()

def looper():
    # Wait until the table has loaded, then detect the minutes column index once.
    wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "tr[role='row'] span.rfkqam4")
        )
    )
    colinfo = get_table_column_indexes()

    while True:

        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "tr[role='row'] span.rfkqam4")
            )
        )

        first_name = driver.find_element(
            By.CSS_SELECTOR,
            "tr[role='row'] span.rfkqam4"
        ).text

        scrape_current_page(colinfo)

        next_btn = driver.find_element(
            By.CSS_SELECTOR,
            "button[aria-label='Next']"
        )

        disabled = (
            next_btn.get_attribute("disabled") is not None
            or next_btn.get_attribute("aria-disabled") == "true"
        )

        if disabled:
            break

        driver.execute_script("arguments[0].click();", next_btn)

        # Wait until page changes
        wait.until(
            lambda d: d.find_element(
                By.CSS_SELECTOR,
                "tr[role='row'] span.rfkqam4"
            ).text != first_name
        )



looper()

df = pd.DataFrame(data)
print("Rows scraped:", len(df))
print(df.head())
df.to_csv("fpl_data.csv", index=False)

driver.quit()