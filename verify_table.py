import sqlite3

conn = sqlite3.connect("data/red_shift.db")
cursor = conn.cursor()

# Check if the table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='QUAL_FINDING';")
result = cursor.fetchone()

if result:
    print("SUCCESS: Table 'QUAL_FINDING' exists in red_shift.db!")
    print("\nColumns inside QUAL_FINDING:")
    # Print the column details
    cursor.execute("PRAGMA table_info(QUAL_FINDING);")
    for col in cursor.fetchall():
        print(f" - {col[1]} ({col[2]})")
else:
    print("FAILED: Table 'QUAL_FINDING' was not found. Please re-run init_database.py.")

conn.close()