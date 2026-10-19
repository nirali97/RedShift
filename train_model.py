import sqlite3
import pandas as pd
import numpy as np
import joblib
import features 
from sklearn.ensemble import RandomForestClassifier

print(">>> STARTING ADVANCED ML PIPELINE <<<")
DB_PATH = "data/red_shift.db"

def prepare_training_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT company_id, fiscal_year, line_item, value FROM FINANCIAL_FACT", conn)
    comp_df = pd.read_sql_query("SELECT company_id, symbol, is_financial FROM COMPANY", conn)
    conn.close()

    X_data, y_data = [], []
    
    for comp_id in df['company_id'].unique():
        if comp_df[comp_df['company_id'] == comp_id]['is_financial'].values[0] == 1: continue
        symbol = comp_df[comp_df['company_id'] == comp_id]['symbol'].values[0]
        
        comp_data = df[df['company_id'] == comp_id]
        pivoted = comp_data.pivot(index="fiscal_year", columns="line_item", values="value")
        years = sorted(pivoted.index)
        
        for i in range(1, len(years)): 
            curr_year, prior_year = years[i], years[i-1]
            curr, prior = pivoted.loc[curr_year].to_dict(), pivoted.loc[prior_year].to_dict()
            
            try:
                b_res = features.compute_beneish(curr, prior)
                m_score, indices = b_res.get('m_score'), b_res.get('indices', {})
                f_score = features.compute_piotroski(curr, prior).get('f_score')
                z_score = features.compute_altman(curr).get('z_score')
            except: continue

            if m_score is None or f_score is None or z_score is None: continue

            row_features = [
                indices.get('DSRI', 1.0), indices.get('GMI', 1.0), indices.get('AQI', 1.0),
                indices.get('SGI', 1.0), indices.get('DEPI', 1.0), indices.get('SGAI', 1.0),
                indices.get('TATA', 0.0), indices.get('LVGI', 1.0)
            ]
            
            # ADVANCED LABEL: Risky if Beneish flags OR Piotroski is weak OR Altman is distress/grey
            is_risky = 1 if (m_score > -1.78 or f_score <= 4 or z_score < 2.60) else 0
            
            X_data.append(row_features)
            y_data.append(is_risky)
            print(f"{symbol} FY{curr_year} -> {'RISKY' if is_risky else 'SAFE'}")

    return np.array(X_data), np.array(y_data)

def train():
    X, y = prepare_training_data()
    if len(X) < 5: return

    model = RandomForestClassifier(n_estimators=100, random_state=42, max_depth=5, class_weight='balanced')
    model.fit(X, y)
    joblib.dump(model, "data/red_shift_risk_model.pkl")
    print("\n>>> SUCCESS! Advanced Model saved. <<<")

if __name__ == "__main__":
    train()