import sqlite3
import os

db_paths = [
    "apps/chat-app/public/assets/llm_fantasy_data.db",
    "shared/llm_fantasy_data.db",
    "suite/original-backend/data/llm_fantasy_data.db"
]

for path in db_paths:
    print(f"Checking {path}...")
    if not os.path.exists(path):
        print("  File not found.")
        continue
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"  Tables: {tables}")
        conn.close()
    except Exception as e:
        print(f"  Error: {e}")
