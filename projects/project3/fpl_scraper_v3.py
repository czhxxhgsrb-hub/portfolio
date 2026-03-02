import time
import requests
import pandas as pd

# ---------------------------
# CONFIG
# ---------------------------
BASE = "https://fantasy.premierleague.com/api"
MIN_TOTAL_MINUTES = 300          # set to 0 if you want everyone
SLEEP_BETWEEN_PLAYERS = 0.0      # set e.g. 0.05 if you hit rate limits
OUTFILE = "fpl_data.csv"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; fpl-api-scraper/1.0)"
})

def get_json(url: str) -> dict:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def main():
    # 1) Load bootstrap (players, teams, positions)
    bootstrap = get_json(f"{BASE}/bootstrap-static/")

    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}
    positions = {p["id"]: p["singular_name"] for p in bootstrap["element_types"]}
    elements = bootstrap["elements"]

    data = []

    for p in elements:
        player_id = p["id"]
        name = f'{p.get("first_name","")} {p.get("second_name","")}'.strip()
        team = teams.get(p.get("team"), str(p.get("team")))
        position = positions.get(p.get("element_type"), str(p.get("element_type")))

        # ✅ PRICE (convert from int to actual price)
        price = (p.get("now_cost") or 0) / 10

        total_minutes = int(p.get("minutes") or 0)
        if total_minutes < MIN_TOTAL_MINUTES:
            continue

        # 2) Per-player match history for THIS season
        summary = get_json(f"{BASE}/element-summary/{player_id}/")
        history = summary.get("history", [])

        for m in history:
            opponent = teams.get(m.get("opponent_team"), str(m.get("opponent_team")))

            data.append({
                "name": name,
                "team": team,
                "position": position,
                "price": price,  # <-- added column

                "gw": m.get("round"),
                "opponent": opponent,
                "home": m.get("was_home"),

                "minutes": m.get("minutes"),
                "points": m.get("total_points"),
                "goals": m.get("goals_scored"),
                "assists": m.get("assists"),

                "xG": m.get("expected_goals", ""),
                "xA": m.get("expected_assists", ""),
                "xGC": m.get("expected_goals_conceded", ""),

                "CS": m.get("clean_sheets", ""),
                "BPS": m.get("bps", ""),
                "YC": m.get("yellow_cards", ""),
                "RC": m.get("red_cards", ""),

                "fixture_id": m.get("fixture", ""),
                "kickoff_time": m.get("kickoff_time", ""),
            })

        if SLEEP_BETWEEN_PLAYERS:
            time.sleep(SLEEP_BETWEEN_PLAYERS)

    df = pd.DataFrame(data)

    print("Rows scraped:", len(df))
    print(df.head())

    df.to_csv(OUTFILE, index=False)
    print(f"Saved to {OUTFILE}")

if __name__ == "__main__":
    main()