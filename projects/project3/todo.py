"""
FPL ML Projection + ILP Optimization Roadmap
=============================================

PHASE 1 — DATA PREPARATION
--------------------------

[X] 1. Load dataset into pandas
[X] 2. Keep only relevant columns:
        - position
        - team
        - price
        - per-match stats (xG_pm, xA_pm, xGI_pm, xGC_pm, S_pm, CS_pm, etc.)
        - points per match (or compute it)
        - minutes (if available)

[X] 3. Compute target variable:
        - PPM = total_points / matches_played
        (if PPM not already provided)

[X] 4. Remove data leakage:
        - Drop total_points
        - Drop cumulative totals
        - Drop price from training features
        - Drop TSB from training features

[X] 5. Remove low-minute players:
        - Filter players with very low minutes (e.g. < 300)
        - Reset index


PHASE 2 — BUILD ML PROJECTION MODEL
------------------------------------

[X] 6. Split dataset by position:
        - GK
        - DEF
        - MID
        - FWD

[X] 7. For each position:
        a) Define features X (all per-match stats)
        b) Define target y = PPM
        c) Train model (LightGBM or RandomForest)
        d) Perform 5-fold cross-validation
        e) Store trained model
        f) Generate predicted_PPM for each player

[X] 8. Combine all position data back together
        - Ensure each player now has predicted_PPM column


PHASE 3 — PREPARE OPTIMIZATION INPUT
-------------------------------------

[X] 9. Create optimization dataframe with:
        - name
        - team
        - position
        - price
        - predicted_PPM

[X] 10. (Optional) Create value metric:
        - value_score = predicted_PPM / price


PHASE 4 — BUILD ILP OPTIMIZER
-----------------------------

[X] 11. Create binary decision variable x_i for each player

[X] 12. Define objective:
        Maximize sum(x_i * predicted_PPM_i)

[X] 13. Add constraints:
        - Total cost <= 100
        - Exactly:
            2 GK
            5 DEF
            5 MID
            3 FWD
        - Max 3 players per real-life team

[X] 14. Solve optimization problem

[X] 15. Extract selected players
        - Print optimal squad
        - Print total projected points
        - Print total cost


PHASE 5 — EVALUATION
--------------------

[X] 16. Compare:
        - Optimized squad
        - Top 15 by raw PPM
        - Top 15 by value_score
        - Most-owned players

[X] 17. Analyze:
        - Which players are model favorites?
        - Which popular players are excluded?
        - Which low-TSB players are included?


PHASE 6 — OPTIONAL EXTENSIONS
-----------------------------

[ ] 18. Add captain variable (double one player's points)
[ ] 19. Add risk adjustment (penalize high variance players)
[ ] 20. Add Monte Carlo simulation of performance variability
[ ] 21. Compare multiple formations (e.g., 3-4-3 vs 3-5-2)
[ ] 22. Save model for next season reuse

"""