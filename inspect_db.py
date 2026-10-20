import sqlite3

c = sqlite3.connect("data/red_shift.db")
tables = [r[0] for r in c.execute(
    "select name from sqlite_master where type='table'")]
print("TABLES:", tables)

for t in tables:
    if t.upper() in ("COMPANY", "SCORE_RUN", "RED_FLAG"):
        continue
    cols = [r[1] for r in c.execute(f"pragma table_info({t})")]
    print("\n==", t, cols)
    if "company_id" not in cols:
        continue
    for row in c.execute(f"select * from {t} where company_id=1"):
        text = " ".join(str(x).lower() for x in row)
        if any(k in text for k in ("sg", "sell", "revenue", "sales")):
            print(row)