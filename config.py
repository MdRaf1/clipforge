import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FOOTAGE_DIR = os.path.join(DATA_DIR, "footage")
OUTPUTS_DIR = os.path.join(DATA_DIR, "outputs")
DB_PATH = os.path.join(DATA_DIR, "clipforge.db")

os.makedirs(FOOTAGE_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)
