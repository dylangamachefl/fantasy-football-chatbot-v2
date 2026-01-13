import sqlite3
import os

db_path = "shared/fantasy_football_wide.db"
print(f"Checking database at: {os.path.abspath(db_path)}")
if not os.path.exists(db_path):
    print("Database file does not exist!")
else:
    print(f"File size: {os.path.getsize(db_path)} bytes")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    print(f"Tables found: {len(tables)}")
    for table in tables:
        count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        print(f"  - {table}: {count} rows")
    conn.close()
