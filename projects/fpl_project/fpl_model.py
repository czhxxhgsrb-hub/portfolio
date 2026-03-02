import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, r2_score
import numpy as np

df = pd.read_csv("fpl_data.csv")

#lidt rengøring
df["home"] = pd.to_numeric(df["home"], errors="coerce").fillna(0).astype(int)
df["minutes"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
numeric_cols = ["gw", "points", "xG", "xA", "shots", "xGC", "BPS"]
for c in numeric_cols:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce")

#sortering
group_key = ["name", "team"] if "team" in df.columns else ["name"]
total_minutes = df.groupby(group_key)["minutes"].transform("sum")

#væk med de små
df = df[total_minutes >= 300].copy()

#sorter igen
df = df.sort_values(group_key + ["gw"]).reset_index(drop=True)

#sæt TARGET, vi leder efter points
df["target_points"] = (
    df.groupby(group_key)["points"]
      .shift(-1)
      .rolling(3)
      .mean()
)

#rulleren
def roll_mean(col, window, new_name):
    df[new_name] = df.groupby(group_key)[col].transform(
        lambda s: s.shift(1).rolling(window, min_periods=window).mean()
    )

#vi skal bruge gennemsnittet for de sidste 3, 5 og 10 kampe for xG (expected Goals), per spiller
#også med 3, 5 for xA, points, minutes, xGC og BPS
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

#vi vil kun have rows med enten relevante features eller target.
feature_cols = [c for c in df.columns if c.startswith("last_")]
df = df.dropna(subset=feature_cols + ["target_points"]).reset_index(drop=True)

#splittet mellem træningsdata og test data
#uge 24 gør at vi har uger 11-24 til træning og 25-27 til test
split_gw = 24
train_df = df[df["gw"] <= split_gw].copy()
test_df = df[df["gw"] > split_gw].copy()

print("Uger der bruges til trænings-data:", train_df["gw"].min(), "-", train_df["gw"].max())
print("Uger der bruges til test-data:", test_df["gw"].min(), "-", test_df["gw"].max())

#definder positioner
positions = ["Forward", "Midfielder", "Defender", "Goalkeeper"]

models = {}
results = {}

#for hver position:
for pos in positions:

    #definer trænings- og test-data i position
    train_pos = train_df[train_df["position"] == pos]
    test_pos = test_df[test_df["position"] == pos]

    if len(train_pos) == 0 or len(test_pos) == 0:
        print(f"Skipping {pos} (not enough data)")
        continue

    X_train = train_pos[feature_cols]
    y_train = train_pos["target_points"]

    X_test = test_pos[feature_cols]
    y_test = test_pos["target_points"]

    #using random-forest regression to model
    model = RandomForestRegressor(
        n_estimators=300,
        random_state=42,
        n_jobs=-1
    )

    model.fit(X_train, y_train)

    preds = model.predict(X_test)

    rmse = np.sqrt(mean_squared_error(y_test, preds))
    r2 = r2_score(y_test, preds)

    models[pos] = model
    results[pos] = {"RMSE": rmse, "R2": r2}

    print(f"\n=== {pos} ===")
    print("Train rows:", len(train_pos))
    print("Test rows:", len(test_pos))
    print("RMSE:", round(rmse, 3))
    print("R2:", round(r2, 3))

print("\nDone training all position models.")

# =========================================
# GENERATE CURRENT PLAYER PROJECTIONS
# =========================================

# 1️⃣ Get latest row per player
latest_df = (
    df.sort_values("gw")
    .groupby(["name", "team"], as_index=False)
    .tail(1)
    .reset_index(drop=True)
)

# 2️⃣ Predict using position-specific models
latest_df["predicted_3match_avg"] = 0.0

for pos in ["Forward", "Midfielder", "Defender", "Goalkeeper"]:

    mask = latest_df["position"] == pos

    if pos in models:
        latest_df.loc[mask, "predicted_3match_avg"] = \
            models[pos].predict(latest_df.loc[mask, feature_cols])

# 3️⃣ Convert to 3-match total projection
latest_df["predicted_points_next_3"] = latest_df["predicted_3match_avg"] * 3

# 4️⃣ Add value metric
latest_df["value_score"] = (
        latest_df["predicted_points_next_3"] / latest_df["price"]
)

print(latest_df[["name", "position", "price",
                 "predicted_points_next_3", "value_score"]]
      .sort_values("predicted_points_next_3", ascending=False)
      .head(10))

import pandas as pd
from pulp import LpProblem, LpVariable, LpMaximize, lpSum, LpBinary, PULP_CBC_CMD

# latest_df must contain at least:
# ["name","team","position","price","predicted_points_next_3"]
latest_df["price"] = pd.to_numeric(latest_df["price"], errors="coerce")
latest_df["predicted_points_next_3"] = pd.to_numeric(latest_df["predicted_points_next_3"], errors="coerce")
latest_df = latest_df.dropna(subset=["price", "predicted_points_next_3"]).reset_index(drop=True)

players = latest_df.index.tolist()

# ----------------------------
# Decision variables
# ----------------------------
squad = LpVariable.dicts("squad", players, cat=LpBinary)   # 15-man squad
start = LpVariable.dicts("start", players, cat=LpBinary)   # starting XI
bench = LpVariable.dicts("bench", players, cat=LpBinary)   # bench (4)
cap   = LpVariable.dicts("cap", players, cat=LpBinary)     # captain (1)

# ----------------------------
# Optimization problem
# ----------------------------
prob = LpProblem("FPL_Squad_XI_Bench_Captain", LpMaximize)

# Objective:
# Maximize starting XI projected points + captain bonus (adds one extra copy of captain points)
prob += (
    lpSum(start[i] * latest_df.loc[i, "predicted_points_next_3"] for i in players)
    + lpSum(cap[i]   * latest_df.loc[i, "predicted_points_next_3"] for i in players)
)

# ----------------------------
# Constraints
# ----------------------------

# Squad size
prob += lpSum(squad[i] for i in players) == 15

# Starting XI size
prob += lpSum(start[i] for i in players) == 11

# Bench size
prob += lpSum(bench[i] for i in players) == 4

# Relationship: if in squad, must be either starting or bench (not both)
for i in players:
    prob += start[i] + bench[i] == squad[i]

# Budget
prob += lpSum(squad[i] * latest_df.loc[i, "price"] for i in players) <= 100

# Max 3 per team (squad constraint)
for team in latest_df["team"].unique():
    prob += lpSum(squad[i] for i in players if latest_df.loc[i, "team"] == team) <= 3

# 15-man position constraints (FPL squad structure)
req_squad = {"Goalkeeper": 2, "Defender": 5, "Midfielder": 5, "Forward": 3}
for pos, required in req_squad.items():
    prob += lpSum(squad[i] for i in players if latest_df.loc[i, "position"] == pos) == required

# ----------------------------
# Starting XI formation: FIXED 4-4-2
# ----------------------------

# Exactly 1 GK starts
prob += lpSum(start[i] for i in players if latest_df.loc[i, "position"] == "Goalkeeper") == 1

# Exactly 4 DEF start
prob += lpSum(start[i] for i in players if latest_df.loc[i, "position"] == "Defender") == 4

# Exactly 4 MID start
prob += lpSum(start[i] for i in players if latest_df.loc[i, "position"] == "Midfielder") == 4

# Exactly 2 FWD start
prob += lpSum(start[i] for i in players if latest_df.loc[i, "position"] == "Forward") == 2

# Bench constraints: exactly 1 GK on bench (since 2 GKs in squad, 1 starts)
prob += lpSum(bench[i] for i in players if latest_df.loc[i, "position"] == "Goalkeeper") == 1

# Captain constraints: exactly 1 captain, must be in starting XI
prob += lpSum(cap[i] for i in players) == 1
for i in players:
    prob += cap[i] <= start[i]

# ----------------------------
# Solve
# ----------------------------
prob.solve(PULP_CBC_CMD(msg=False))

# ----------------------------
# Extract results
# ----------------------------
squad_idx = [i for i in players if squad[i].value() == 1]
start_idx = [i for i in players if start[i].value() == 1]
bench_idx = [i for i in players if bench[i].value() == 1]
cap_idx   = [i for i in players if cap[i].value() == 1]

squad_df = latest_df.loc[squad_idx, ["name","position","team","price","predicted_points_next_3"]].copy()
start_df = latest_df.loc[start_idx, ["name","position","team","price","predicted_points_next_3"]].copy()
bench_df = latest_df.loc[bench_idx, ["name","position","team","price","predicted_points_next_3"]].copy()
cap_df   = latest_df.loc[cap_idx,   ["name","position","team","price","predicted_points_next_3"]].copy()

# Helpful sorting
pos_order = {"Goalkeeper": 0, "Defender": 1, "Midfielder": 2, "Forward": 3}
for d in (squad_df, start_df, bench_df, cap_df):
    d["pos_order"] = d["position"].map(pos_order)

squad_df = squad_df.sort_values(["pos_order","predicted_points_next_3"], ascending=[True, False]).drop(columns=["pos_order"])
start_df = start_df.sort_values(["pos_order","predicted_points_next_3"], ascending=[True, False]).drop(columns=["pos_order"])
bench_df = bench_df.sort_values(["pos_order","predicted_points_next_3"], ascending=[True, False]).drop(columns=["pos_order"])
cap_df   = cap_df.drop(columns=["pos_order"])

print("\n=== FULL SQUAD (15) ===\n")
print(squad_df.to_string(index=False))

print("\n=== STARTING XI ===\n")
print(start_df.to_string(index=False))

print("\n=== BENCH (4) ===\n")
print(bench_df.to_string(index=False))

print("\n=== CAPTAIN (must be starter) ===\n")
print(cap_df.to_string(index=False))

total_cost = squad_df["price"].sum()
xi_points = start_df["predicted_points_next_3"].sum()
cap_bonus = float(cap_df["predicted_points_next_3"].iloc[0]) if len(cap_df) else 0.0

print("\nTotal Cost:", round(total_cost, 2))
print("Projected Points next 3 (XI only):", round(xi_points, 2))
print("Projected Points next 3 (XI + captain bonus):", round(xi_points + cap_bonus, 2))