import os

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
SAVE_DEBUG_HTML = os.getenv("SAVE_DEBUG_HTML", "false").lower() == "true"

API_KEY = os.getenv("API_KEY", "")
IP_ALLOWLIST = os.getenv("IP_ALLOWLIST", "*").split(",")

ORACLE_DSN = os.getenv("ORACLE_DSN", "")
ORACLE_USER = os.getenv("ORACLE_USER", "")
ORACLE_PASSWORD = os.getenv("ORACLE_PASSWORD", "")