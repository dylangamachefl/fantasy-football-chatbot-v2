import sqlite3

import os

# Use absolute paths to avoid confusion
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE_DB = os.path.join(BASE_DIR, "shared", "llm_fantasy_data.db")
TARGET_DB = os.path.join(BASE_DIR, "shared", "fantasy_football_wide.db")

# The 8 optimized tables to migrate
TABLES_TO_MIGRATE = [
    "Fact_Player_Performance_Weekly",
    "Fact_Player_Season_Stat_Leaders",
    "Fact_Matchup_History_Wide",
    "Fact_Draft_Performance_Analysis",
    "Fact_Team_Season_Standings",
    "Fact_Manager_Career_Leaderboard",
    "Fact_Player_Master_Profile",
    "Players_Wide"
]

def run_migration():
    src_conn = sqlite3.connect(SOURCE_DB)
    tgt_conn = sqlite3.connect(TARGET_DB)
    tgt_conn.execute(f"ATTACH DATABASE '{SOURCE_DB}' AS source")
    
    print("Starting wide-table materialization...")
    
    for table in TABLES_TO_MIGRATE:
        print(f"Materializing {table}...")
        # Check if it's a table or view and drop accordingly
        type_res = tgt_conn.execute(f"SELECT type FROM sqlite_master WHERE name='{table}'").fetchone()
        if type_res:
            obj_type = type_res[0].upper()
            tgt_conn.execute(f"DROP {obj_type} IF EXISTS {table}")
            
        tgt_conn.execute(f"CREATE TABLE {table} AS SELECT * FROM source.{table}")
        
        # Fixed Indexing Logic: Treating owner_name and manager_name as the same entity
        cols = [c[1] for c in tgt_conn.execute(f"PRAGMA table_info({table})")]
        
        if "player_id" in cols:
            tgt_conn.execute(f"CREATE INDEX idx_{table}_player_id ON {table}(player_id)")
        
        # Check for either naming convention and apply index to the same logical manager field
        if "owner_name" in cols:
            tgt_conn.execute(f"CREATE INDEX idx_{table}_owner ON {table}(owner_name)")
        elif "manager_name" in cols:
            tgt_conn.execute(f"CREATE INDEX idx_{table}_manager ON {table}(manager_name)")
            
        if "season_id" in cols:
            tgt_conn.execute(f"CREATE INDEX idx_{table}_season ON {table}(season_id)")
                
    tgt_conn.commit()
    print(f"\nMigration finished. Agent-ready database: {TARGET_DB}")
    src_conn.close()
    tgt_conn.close()

if __name__ == "__main__":
    run_migration()