import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

driver = webdriver.Firefox()
driver.get("https://fantasy.premierleague.com/statistics")
wait = WebDriverWait(driver, 15)

players = []

#scrape ÉN side
def scrape_page():
    rows = driver.find_elements(By.CSS_SELECTOR, "tr[role='row']")
    for row in rows:
        try:
            name = row.find_element(By.CSS_SELECTOR, "span.rfkqam4").text
            team = row.find_element(By.CSS_SELECTOR, "span.rfkqam3 span:nth-child(1)").text
            position = row.find_element(By.CSS_SELECTOR, "span.rfkqam3 span:nth-child(2)").text
            cells = row.find_elements(By.CSS_SELECTOR, "td[role='gridcell']")

            players.append({
                "name": name,
                "team": team,
                "position": position,
                "price": cells[0].text,
                "tsb": cells[1].text,
                "form": cells[2].text,
                "tp": cells[3].text
            })
        except:
            pass

#fuck cookies
try:
        wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
except:
        pass

#scrape loop
while True:
    wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "tr[role='row']")))

    first_name = driver.find_element(By.CSS_SELECTOR, "tr[role='row'] span.rfkqam4").text
    scrape_page()

    next_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Next']")

    if next_btn.get_attribute("disabled") or next_btn.get_attribute("aria-disabled") == "true":
        break

    next_btn.click()
    wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "tr[role='row'] span.rfkqam4").text != first_name)

df = pd.DataFrame(players)
print(len(df))
driver.quit()