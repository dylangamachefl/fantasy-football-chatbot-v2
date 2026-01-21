import json
import os
import subprocess
import sys
import pandas as pd

# Paths
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SHARED_DIR = os.path.join(ROOT_DIR, "shared")
GOLDEN_DATASET_PATH = os.path.join(SHARED_DIR, "golden_dataset.json")
LOGS_DIR = os.path.join(ROOT_DIR, "logs")

def load_golden_dataset():
    if not os.path.exists(GOLDEN_DATASET_PATH):
        return []
    with open(GOLDEN_DATASET_PATH, 'r') as f:
        return json.load(f)

def save_golden_dataset(data):
    os.makedirs(os.path.dirname(GOLDEN_DATASET_PATH), exist_ok=True)
    with open(GOLDEN_DATASET_PATH, 'w') as f:
        json.dump(data, f, indent=2)

def list_logs():
    if not os.path.exists(LOGS_DIR):
        return []
    logs = []
    for filename in os.listdir(LOGS_DIR):
        if filename.endswith(".json"):
            logs.append(filename)
    return sorted(logs, reverse=True)

def load_log_file(filename):
    path = os.path.join(LOGS_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)

def load_compiled_artifact():
    path = os.path.join(ROOT_DIR, "suite", "evaluation", "compiled_fantasy_agent.json")
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        return json.load(f)

def get_signature_info(sig_class):
    """
    Extract docstring and fields from a DSPy Signature class.
    """
    import dspy
    info = {
        "doc": sig_class.__doc__.strip() if sig_class.__doc__ else "No description.",
        "inputs": [],
        "outputs": []
    }
    
    # DSPy signature fields are stored in _fields
    for name, field in sig_class.fields.items():
        field_info = {
            "name": name,
            "description": field.json_schema_extra.get('desc', "") if field.json_schema_extra else ""
        }
        if isinstance(field, dspy.InputField):
            info["inputs"].append(field_info)
        else:
            info["outputs"].append(field_info)
            
    return info

def run_script(script_path):
    """
    Run a python script and yield its output line by line.
    """
    cmd = [sys.executable, script_path]
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=ROOT_DIR
    )
    
    for line in process.stdout:
        yield line
    
    process.wait()
    if process.returncode != 0:
        yield f"ERROR: Script failed with return code {process.returncode}\n"
