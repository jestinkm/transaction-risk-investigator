"""
Generates synthetic customer transaction histories for PS06.
Run once: python scripts/generate_data.py
Writes CSVs to data/customers/. Already committed, so judges don't need to re-run this.

Design note: the first WARMUP_DAYS days deliberately touch every payee and
category at least twice, so that by the rule engine's BASELINE_DAYS cutoff
every "normal" payee/category has already been seen. This mirrors how the
rules themselves are written (R2/R4 refuse to call something "new" without
an established baseline) and avoids injecting false anomalies purely from
random draw order.
"""
import csv
import os
import random
from datetime import datetime, timedelta

random.seed(42)

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "customers")
os.makedirs(OUT_DIR, exist_ok=True)

CATEGORIES = ["groceries", "utilities", "dining", "fuel", "shopping", "subscription", "rent", "salary_credit"]
CHANNELS = ["UPI", "card", "netbanking", "ATM"]
PAYEES_POOL = [
    "Big Bazaar Retail", "State Electricity Board", "Swiggy", "HP Petrol Pump",
    "Amazon Retail", "Netflix India", "Landlord - R. Iyer", "Employer Payroll",
    "Zomato", "Local Kirana Store", "Airtel Postpaid", "BookMyShow"
]

START = datetime(2026, 6, 1)
DAYS = 90
WARMUP_DAYS = 14    # every normal payee/category is seeded within this window
BASELINE_DAYS = 30  # must match risk_rules.json baseline_days


def rand_time(odd=False):
    if odd:
        h = random.randint(0, 4)
    else:
        h = random.choice(list(range(6, 23)))
    m = random.randint(0, 59)
    return h, m


def make_txn(day_offset, payee, category, amount, channel, odd=False):
    date = START + timedelta(days=day_offset)
    h, m = rand_time(odd=odd)
    return {
        "txn_id": "TMP",
        "date": date.strftime("%Y-%m-%d"),
        "time": f"{h:02d}:{m:02d}",
        "description": payee,
        "payee": payee,
        "amount": round(amount, 2),
        "channel": channel,
        "category": category,
    }


def warmup_txns(payees, categories, amount_range=(200, 4000)):
    """Guarantees every payee and every category appears at least twice within
    the first WARMUP_DAYS days, well before the rule engine's baseline cutoff."""
    txns = []
    entries = list(payees) * 2
    random.shuffle(entries)
    for i, payee in enumerate(entries):
        day = i % WARMUP_DAYS
        category = categories[i % len(categories)]
        txns.append(make_txn(day, payee, category, random.uniform(*amount_range), random.choice(CHANNELS)))
    for i, cat in enumerate(categories * 2):
        day = i % WARMUP_DAYS
        payee = random.choice(payees)
        txns.append(make_txn(day, payee, cat, random.uniform(*amount_range), random.choice(CHANNELS)))
    return txns


def random_txns(start_day, end_day, payees, categories, amount_range=(200, 4000),
                 n_per_day_range=(0, 3), odd_hour_share=0.0):
    txns = []
    for d in range(start_day, end_day):
        n = random.randint(*n_per_day_range)
        for _ in range(n):
            odd = random.random() < odd_hour_share
            payee = random.choice(payees)
            category = random.choice(categories)
            amount = random.uniform(*amount_range)
            txns.append(make_txn(d, payee, category, amount, random.choice(CHANNELS), odd=odd))
    return txns


def base_transactions(payees=None, categories=None, amount_range=(200, 4000), odd_hour_share=0.0):
    payees = payees or PAYEES_POOL
    categories = categories or CATEGORIES
    return (
        warmup_txns(payees, categories, amount_range)
        + random_txns(WARMUP_DAYS, DAYS, payees, categories, amount_range, odd_hour_share=odd_hour_share)
    )


def write_csv(name, txns):
    """Sorts chronologically and assigns final sequential txn_ids, so every
    generation path (warmup / random / injected anomaly) is free to ignore
    txn_id entirely until this point."""
    txns = sorted(txns, key=lambda t: (t["date"], t["time"]))
    for i, t in enumerate(txns, start=1):
        t["txn_id"] = f"T{i:05d}"
    path = os.path.join(OUT_DIR, f"{name}.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["txn_id", "date", "time", "description", "payee", "amount", "channel", "category"])
        w.writeheader()
        w.writerows(txns)
    print(f"wrote {path} ({len(txns)} txns)")


# --- Customer 1: clean, routine history ---
c1 = base_transactions()
write_csv("cust_101_clean", c1)

# --- Customer 2: large transfer outlier (well after baseline) ---
c2 = base_transactions()
c2.append(make_txn(70, "Unknown Pvt Ltd", "shopping", 385000.00, "netbanking"))
write_csv("cust_102_large_transfer", c2)

# --- Customer 3: new payee burst (payee never seen before, appears only after baseline) ---
c3 = base_transactions()
new_payee = "QuickCash Lending Co"
for i in range(4):
    c3.append(make_txn(80 + i, new_payee, "shopping", 9000.00 + i * 500, "UPI"))
write_csv("cust_103_new_payee_burst", c3)

# --- Customer 4: odd hours activity (customer with no odd-hour history at all) ---
c4 = base_transactions(odd_hour_share=0.0)
for i in range(3):
    c4.append(make_txn(75 + i, "ATM Network", "shopping", 15000.00, "ATM", odd=True))
write_csv("cust_104_odd_hours", c4)

# --- Customer 5: pattern break (new category, never seen even in warmup, above-median amount) ---
c5 = base_transactions(categories=["groceries", "utilities", "dining", "salary_credit"], amount_range=(300, 2500))
c5.append(make_txn(85, "CryptoXchange Ltd", "crypto_exchange", 62000.00, "netbanking"))
write_csv("cust_105_pattern_break", c5)

print("done")
