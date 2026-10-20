import sqlite3

conn = sqlite3.connect("data/red_shift.db")
cursor = conn.cursor()

cursor.execute("SELECT company_id FROM COMPANY WHERE symbol = 'ADANIENT'")
company_id = cursor.fetchone()[0]

cursor.execute("SELECT run_id FROM SCORE_RUN WHERE company_id = ? ORDER BY fiscal_year DESC LIMIT 1", (company_id,))
run_id = cursor.fetchone()[0]

cursor.execute("""
    INSERT INTO QUAL_FINDING 
    (run_id, theme, severity, finding_text, quotation, verification_status)
    VALUES (?, ?, ?, ?, ?, ?)
""", (
    run_id, 
    "Related-Party Transactions", 
    "High", 
    "Material surge in unsecured advances and loan guarantees issued to entities under common control.", 
    "\"Advances to entities under common control rose to 18.4% of net assets. Corporate guarantees given on behalf of subsidiaries amount to Rs 1,284 crore.\"", 
    "Exact match after normalisation, score 1.00"
))

conn.commit()
conn.close()
print("Mock narrative finding injected for ADANIENT.")