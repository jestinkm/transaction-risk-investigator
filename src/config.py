import os

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
LLM_MODEL = os.environ.get("GEMINI_LLM_MODEL", "gemini-2.0-flash")
EMBED_MODEL = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
CUSTOMERS_DIR = os.path.join(DATA_DIR, "customers")
RULES_PATH = os.path.join(DATA_DIR, "risk_rules.json")

HOST = "0.0.0.0"
PORT = 8000
