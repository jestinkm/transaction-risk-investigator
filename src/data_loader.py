import csv
import glob
import json
import os
from src import config


def list_customers():
    """Returns [{id, label}] for every CSV in data/customers/."""
    out = []
    for path in sorted(glob.glob(os.path.join(config.CUSTOMERS_DIR, "*.csv"))):
        cust_id = os.path.splitext(os.path.basename(path))[0]
        label = cust_id.replace("_", " ").title()
        out.append({"id": cust_id, "label": label})
    return out


def load_transactions(customer_id: str):
    path = os.path.join(config.CUSTOMERS_DIR, f"{customer_id}.csv")
    if not os.path.exists(path):
        return None
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            r["amount"] = float(r["amount"])
            rows.append(r)
    rows.sort(key=lambda r: (r["date"], r["time"]))
    return rows


def load_rules():
    with open(config.RULES_PATH) as f:
        return json.load(f)


def rules_by_id():
    return {r["rule_id"]: r for r in load_rules()}
