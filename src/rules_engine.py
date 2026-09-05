"""
Deterministic risk-rule evaluation. No LLM calls happen in this file.
Given a customer's transaction history, each rule function returns a list of
"findings" — every finding names the exact transaction ids that triggered it
and the arithmetic behind the trigger, so nothing here can hallucinate: a
finding either points at real rows in the input or it doesn't exist.
"""
import statistics
from collections import defaultdict
from datetime import datetime

from src import payee_normalizer


def _dt(row):
    return datetime.strptime(f"{row['date']} {row['time']}", "%Y-%m-%d %H:%M")


def _median_amount(transactions):
    amounts = [t["amount"] for t in transactions]
    return statistics.median(amounts) if amounts else 0.0


def rule_large_transfer(transactions, rule):
    p = rule["params"]
    median = _median_amount(transactions)
    threshold = max(median * p["multiplier_of_median"], p["absolute_floor"])
    hits = [t for t in transactions if t["amount"] > threshold]
    if not hits:
        return None
    return {
        "rule_id": rule["rule_id"],
        "rule_title": rule["title"],
        "rule_text": rule["text"],
        "transactions_involved": [t["txn_id"] for t in hits],
        "evidence": {
            "customer_median_amount": round(median, 2),
            "trigger_threshold": round(threshold, 2),
            "flagged_transactions": [
                {"txn_id": t["txn_id"], "date": t["date"], "amount": t["amount"], "payee": t["payee"]}
                for t in hits
            ],
        },
        "deviation_explanation": (
            f"Flagged amount(s) exceed this customer's own median transaction "
            f"({round(median, 2)}) by more than {p['multiplier_of_median']}x, "
            f"and clear the {p['absolute_floor']} floor."
        ),
    }


def rule_new_payee_burst(transactions, rule):
    p = rule["params"]
    canonical_map = payee_normalizer.build_canonical_payee_map([t["description"] for t in transactions])
    by_payee = defaultdict(list)
    for t in transactions:
        by_payee[canonical_map[t["description"]]].append(t)

    dataset_start = min(_dt(t) for t in transactions)
    baseline_cutoff = dataset_start.date()
    from datetime import timedelta as _td
    baseline_cutoff = dataset_start + _td(days=p["baseline_days"])

    median = _median_amount(transactions)
    findings_txns = []
    detail_lines = []

    for payee_id, txns in by_payee.items():
        txns = sorted(txns, key=_dt)
        first_seen = _dt(txns[0])
        if first_seen <= baseline_cutoff:
            # First appeared during the baseline window itself — no prior history to
            # compare against, so we can't call this "new" with any confidence.
            continue
        # every transaction to a genuinely new payee is in scope for burst detection
        new_window_txns = txns
        if len(new_window_txns) < 2:
            continue
        # slide a burst_window_days window across the new-payee transactions
        for i, anchor in enumerate(new_window_txns):
            window = [t for t in new_window_txns if 0 <= (_dt(t) - _dt(anchor)).days <= p["burst_window_days"]]
            total = sum(t["amount"] for t in window)
            if len(window) >= p["burst_count"] or total > median * p["burst_amount_multiplier"]:
                ids = [t["txn_id"] for t in window]
                if not set(ids).issubset(set(findings_txns)):
                    findings_txns.extend([i for i in ids if i not in findings_txns])
                    detail_lines.append(
                        f"Payee first seen {first_seen.date()}: {len(window)} txns totalling "
                        f"{round(total, 2)} within {p['burst_window_days']} days (payee desc: "
                        f"'{txns[0]['description']}')."
                    )
                break

    if not findings_txns:
        return None
    return {
        "rule_id": rule["rule_id"],
        "rule_title": rule["title"],
        "rule_text": rule["text"],
        "transactions_involved": findings_txns,
        "evidence": {"customer_median_amount": round(median, 2), "clusters": detail_lines},
        "deviation_explanation": (
            "One or more payees with no prior history before this customer's established "
            f"{p['baseline_days']}-day baseline received a burst of payments meeting the "
            f"{p['burst_count']}-transaction or {p['burst_amount_multiplier']}x-median threshold."
        ),
    }


def rule_odd_hours(transactions, rule):
    p = rule["params"]

    def is_odd(t):
        h = int(t["time"].split(":")[0])
        return p["window_start_hour"] <= h < p["window_end_hour"]

    odd_txns = [t for t in transactions if is_odd(t)]
    share = len(odd_txns) / len(transactions) if transactions else 0.0
    if not odd_txns or share >= p["customer_historical_share_threshold"]:
        return None
    return {
        "rule_id": rule["rule_id"],
        "rule_title": rule["title"],
        "rule_text": rule["text"],
        "transactions_involved": [t["txn_id"] for t in odd_txns],
        "evidence": {
            "odd_hour_txn_count": len(odd_txns),
            "total_txn_count": len(transactions),
            "odd_hour_share": round(share, 4),
            "flagged_transactions": [
                {"txn_id": t["txn_id"], "date": t["date"], "time": t["time"], "amount": t["amount"]}
                for t in odd_txns
            ],
        },
        "deviation_explanation": (
            f"Only {round(share * 100, 2)}% of this customer's history falls in the "
            f"{p['window_start_hour']:02d}:00\u2013{p['window_end_hour']:02d}:00 window "
            f"(threshold: {p['customer_historical_share_threshold'] * 100:.0f}%), so this is not their normal pattern."
        ),
    }


def rule_pattern_break(transactions, rule):
    p = rule["params"]
    median = _median_amount(transactions)

    from datetime import timedelta as _td
    dataset_start = min(_dt(t) for t in transactions)
    baseline_cutoff = dataset_start + _td(days=p["baseline_days"])

    by_date = sorted(transactions, key=_dt)
    seen_categories = {t["category"] for t in by_date if _dt(t) <= baseline_cutoff}
    hits = []
    for t in by_date:
        if _dt(t) <= baseline_cutoff:
            continue
        cat = t["category"]
        if cat not in seen_categories:
            if t["amount"] > median:
                hits.append((t, cat))
            seen_categories.add(cat)

    if not hits:
        return None
    return {
        "rule_id": rule["rule_id"],
        "rule_title": rule["title"],
        "rule_text": rule["text"],
        "transactions_involved": [t["txn_id"] for t, _ in hits],
        "evidence": {
            "customer_median_amount": round(median, 2),
            "flagged_transactions": [
                {"txn_id": t["txn_id"], "date": t["date"], "amount": t["amount"],
                 "new_category": cat, "payee": t["payee"]}
                for t, cat in hits
            ],
        },
        "deviation_explanation": (
            "Category never seen before in this customer's history, paired with an "
            "above-median amount \u2014 a new category alone would not trigger this rule."
        ),
    }


RULE_FUNCS = {
    "R1_LARGE_TRANSFER": rule_large_transfer,
    "R2_NEW_PAYEE_BURST": rule_new_payee_burst,
    "R3_ODD_HOURS": rule_odd_hours,
    "R4_PATTERN_BREAK": rule_pattern_break,
}


def evaluate(transactions, rules):
    """Runs every rule against the transaction list. Returns a list of findings
    (empty list means the history came back clean)."""
    findings = []
    for rule in rules:
        func = RULE_FUNCS.get(rule["rule_id"])
        if not func:
            continue
        result = func(transactions, rule)
        if result:
            findings.append(result)
    return findings
