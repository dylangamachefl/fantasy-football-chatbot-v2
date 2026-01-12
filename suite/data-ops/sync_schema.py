import csv
import json
import os

def sync_schema():
    table_dict_path = "suite/original-backend/data/table_dictionary.csv"
    data_dict_path = "suite/original-backend/data/data_dictionary.csv"
    output_path = "apps/chat-app/public/assets/schema.json"

    if not os.path.exists(table_dict_path) or not os.path.exists(data_dict_path):
        print(f"Error: Dictionary files not found.")
        return

    tables = {}

    # Load table descriptions
    with open(table_dict_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            table_name = row['table_name']
            tables[table_name] = {
                "description": row['table_description'],
                "columns": []
            }

    # Load column descriptions
    with open(data_dict_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            table_name = row['table_name']
            if table_name in tables:
                tables[table_name]['columns'].append({
                    "name": row['column_name'],
                    "description": row['column_description']
                })

    # Ensure the directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(tables, f, indent=2)

    print(f"Successfully synced schema to {output_path}")

if __name__ == "__main__":
    sync_schema()
