import json
import pandas as pd
import numpy as np

from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score

# Optional: comment out if you don't want optimal squad output
from pulp import LpProblem, LpVariable, LpMaximize, lpSum, LpBinary, PULP_CBC_CMD


import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_IN = os.path.join(BASE_DIR, "fpl_data.csv")
OUT_PROJECTIONS = "projections.json"
OUT_OPTIMAL_442 = "optimal_442.json"

MIN_TOTAL_MINUTES = 300
SPLIT_GW = 24  # same idea as your current script


def build_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    df = df.copy()

    # Basic cleaning (mirrors your script)
    df["home"] = pd.to_numeric(df["home"], errors="coerce").fillna(0).astype(int)
    df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")

    # Ensure numeric for these columns if present
    numeric_cols = ["gw", "points", "xG", "xA", "xGC", "BPS"]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    group_key = ["name", "team"] if "team" in df.columns else ["name"]

    # Remove low-minute players
    total_minutes = df.groupby(group_key)["minutes"].transform("sum")
    df = df[total_minutes >= MIN_TOTAL_MINUTES].copy()

    # Sort
    df = df.sort_values(group_key + ["gw"]).reset_index(drop=True)

    # Target: next-3-match average (same idea as your code)
    df["target_points"] = (
        df.groupby(group_key)["points"]
          .shift(-1)
          .rolling(3)
          .mean()
    )

    def roll_mean(col, window, new_name):
        if col not in df.columns:
            return
        df[new_name] = df.groupby(group_key)[col].transform(
            lambda s: s.shift(1).rolling(window, min_periods=window).mean()
        )

    # Rolling features (subset of yours; keep/extend freely)
    roll_mean("xG", 3,  "last_3_xG")
    roll_mean("xG", 5,  "last_5_xG")
    roll_mean("xG", 10, "last_10_xG")
    roll_mean("xA", 3,  "last_3_xA")
    roll_mean("xA", 5,  "last_5_xA")
    roll_mean("points", 3, "last_3_points")
    roll_mean("points", 5, "last_5_points")
    roll_mean("minutes", 3, "last_3_minutes")
    roll_mean("minutes", 5, "last_5_minutes")
    roll_mean("xGC", 5, "last_5_xGC")
    roll_mean("BPS", 3, "last_3_BPS")

    feature_cols = [c for c in df.columns if c.startswith("last_")]
    df = df.dropna(subset=feature_cols + ["target_points", "price"]).reset_index(drop=True)

    return df, feature_cols, group_key


def train_models(df: pd.DataFrame, feature_cols: list[str]) -> dict:
    train_df = df[df["gw"] <= SPLIT_GW].copy()
    test_df = df[df["gw"] > SPLIT_GW].copy()

    positions = ["Forward", "Midfielder", "Defender", "Goalkeeper"]
    models = {}

    # Train per position
    for pos in positions:
        train_pos = train_df[train_df["position"] == pos]
        test_pos = test_df[test_df["position"] == pos]

        if len(train_pos) < 50:
            print(f"Skipping {pos}: not enough train rows ({len(train_pos)})")
            continue

        X_train = train_pos[feature_cols]
        y_train = train_pos["target_points"]

        model = RandomForestRegressor(
            n_estimators=300,
            random_state=42,
            n_jobs=-1
        )
        model.fit(X_train, y_train)
        models[pos] = model

        # quick eval (optional)
        if len(test_pos) > 0:
            preds = model.predict(test_pos[feature_cols])
            rmse = float(np.sqrt(mean_squared_error(test_pos["target_points"], preds)))
            r2 = float(r2_score(test_pos["target_points"], preds))
            print(f"{pos}: RMSE={rmse:.3f} R2={r2:.3f} test_rows={len(test_pos)}")

    return models


def make_projections(df: pd.DataFrame, feature_cols: list[str], group_key: list[str], models: dict) -> pd.DataFrame:
    # Latest row per player
    latest_df = (
        df.sort_values("gw")
          .groupby(group_key, as_index=False)
          .tail(1)
          .reset_index(drop=True)
    )

    latest_df["predicted_3match_avg"] = 0.0

    for pos, model in models.items():
        mask = latest_df["position"] == pos
        if mask.any():
            latest_df.loc[mask, "predicted_3match_avg"] = model.predict(latest_df.loc[mask, feature_cols])

    latest_df["predicted_points_next_3"] = latest_df["predicted_3match_avg"] * 3
    latest_df["value_score"] = latest_df["predicted_points_next_3"] / latest_df["price"]

    cols = ["name", "team", "position", "price", "predicted_points_next_3", "value_score"]
    latest_df = latest_df[cols].copy()

    latest_df = latest_df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
    return latest_df


def optimize_442(latest_df: pd.DataFrame) -> dict:
    # ILP like your PuLP section, fixed 4-4-2
    latest_df = latest_df.copy()
    latest_df["price"] = pd.to_numeric(latest_df["price"], errors="coerce")
    latest_df["predicted_points_next_3"] = pd.to_numeric(latest_df["predicted_points_next_3"], errors="coerce")
    latest_df = latest_df.dropna(subset=["price", "predicted_points_next_3"]).reset_index(drop=True)

    players = latest_df.index.tolist()

    squad = LpVariable.dicts("squad", players, cat=LpBinary)
    start = LpVariable.dicts("start", players, cat=LpBinary)
    bench = LpVariable.dicts("bench", players, cat=LpBinary)
    cap   = LpVariable.dicts("cap", players, cat=LpBinary)

    prob = LpProblem("FPL_Squad_XI_Bench_Captain", LpMaximize)

    prob += (
        lpSum(start[i] * latest_df.loc[i, "predicted_points_next_3"] for i in players) +
        lpSum(cap[i]   * latest_df.loc[i, "predicted_points_next_3"] for i in players)
    )

    prob += lpSum(squad[i] for i in players) == 15
    prob += lpSum(start[i] for i in players) == 11
    prob += lpSum(bench[i] for i in players) == 4

    for i in players:
        prob += start[i] + bench[i] == squad[i]

    prob += lpSum(squad[i] * latest_df.loc[i, "price"] for i in players) <= 100

    for team in latest_df["team"].unique():
        prob += lpSum(squad[i] for i in players if latest_df.loc[i, "team"] == team) <= 3

    req_squad = {"Goalkeeper": 2, "Defender": 5, "Midfielder": 5, "Forward": 3}
    for pos, required in req_squad.items():
        prob += lpSum(squad[i] for i in players if latest_df.loc[i, "position"] == pos) == required

    prob += lpSum(start[i] for i in players if latest_df.loc[i, "position"] == "Goalkeeper") == 1
    prob += lpSum(start[i] for i in players if latest_df.loc[i, "position"] == "Defender") == 4
    prob += lpSum(start[i] for i in players if latest_df.loc[i, "position"] == "Midfielder") == 4
    prob += lpSum(start[i] for i in players if latest_df.loc[i, "position"] == "Forward") == 2

    prob += lpSum(bench[i] for i in players if latest_df.loc[i, "position"] == "Goalkeeper") == 1

    prob += lpSum(cap[i] for i in players) == 1
    for i in players:
        prob += cap[i] <= start[i]

    prob.solve(PULP_CBC_CMD(msg=False))

    def selected(var_dict):
        return [i for i in players if var_dict[i].value() == 1]

    squad_idx = selected(squad)
    start_idx = selected(start)
    bench_idx = selected(bench)
    cap_idx   = selected(cap)

    def rows(idxs):
        return latest_df.loc[idxs, ["name", "team", "position", "price", "predicted_points_next_3"]].to_dict("records")

    squad_rows = rows(squad_idx)
    start_rows = rows(start_idx)
    bench_rows = rows(bench_idx)
    cap_rows   = rows(cap_idx)

    total_cost = float(sum(p["price"] for p in squad_rows))
    xi_points = float(sum(p["predicted_points_next_3"] for p in start_rows))
    cap_bonus = float(cap_rows[0]["predicted_points_next_3"]) if cap_rows else 0.0

    return {
        "formation": "4-4-2",
        "squad": squad_rows,
        "starting_xi": start_rows,
        "bench": bench_rows,
        "captain": cap_rows[0] if cap_rows else None,
        "totals": {
            "total_cost": round(total_cost, 2),
            "xi_points_next_3": round(xi_points, 2),
            "xi_plus_captain_next_3": round(xi_points + cap_bonus, 2),
        },
    }


def main():
    df = pd.read_csv(CSV_IN)

    df_feat, feature_cols, group_key = build_features(df)
    models = train_models(df_feat, feature_cols)
    projections = make_projections(df_feat, feature_cols, group_key, models)

    # Write projections for the website
    projections.to_json(OUT_PROJECTIONS, orient="records")
    print(f"Wrote {OUT_PROJECTIONS} rows={len(projections)}")

    # Write optimal 4-4-2 (optional but nice)
    optimal = optimize_442(projections)
    with open(OUT_OPTIMAL_442, "w", encoding="utf-8") as f:
        json.dump(optimal, f, ensure_ascii=False, indent=2)
    print(f"Wrote {OUT_OPTIMAL_442}")


if __name__ == "__main__":
    main()