"""
Turns rules_engine findings into the final report shape the UI/judge sees.
The LLM's job is narrow and constrained: turn already-computed, already-cited
findings into an investigator-readable narrative. It is never given license to
introduce a transaction, a rule, or a conclusion that isn't already in the
findings list, and the prompt explicitly forbids stating that fraud occurred.
If the LLM call fails for any reason, a deterministic template produces an
equivalent (plainer) narrative so the report is never blocked on the network.
"""
from src import gemini_client

FRAUD_LANGUAGE_GUARD = (
    "You are drafting investigator-facing notes, not a verdict. Never state or imply "
    "that fraud has occurred. Only describe what the data shows and what the rule "
    "flags; the investigator decides what it means. Do not invent any transaction, "
    "amount, date, or rule that is not explicitly given to you below."
)


def _prompt_for_finding(customer_id, finding):
    return f"""{FRAUD_LANGUAGE_GUARD}

Customer: {customer_id}
Rule triggered: {finding['rule_id']} - {finding['rule_title']}
Rule text (quote/paraphrase only from this): "{finding['rule_text']}"
Deterministic deviation explanation: {finding['deviation_explanation']}
Transactions involved: {finding['transactions_involved']}
Evidence: {finding['evidence']}

Write 2-3 sentences for an investigator: what the transactions show, how they connect to
each other, and what specifically to look at first. Do not restate the rule text verbatim;
paraphrase it naturally. Do not add any transaction id not listed above.
"""


def _fallback_narrative(finding):
    return (
        f"{finding['rule_title']} ({finding['rule_id']}) triggered on "
        f"{len(finding['transactions_involved'])} transaction(s): "
        f"{', '.join(finding['transactions_involved'])}. {finding['deviation_explanation']} "
        f"Start by reviewing these transactions against the customer's account notes."
    )


def _narrative_for_finding(customer_id, finding):
    text = gemini_client.generate_text(_prompt_for_finding(customer_id, finding), max_output_tokens=200)
    used_llm = text is not None
    return (text if text else _fallback_narrative(finding)), used_llm


def _overall_narrative(customer_id, findings):
    if not findings:
        return "No transactions in this history triggered any of the configured risk rules. Nothing here warrants investigator attention at this time.", False
    prompt = f"""{FRAUD_LANGUAGE_GUARD}

Customer: {customer_id}
{len(findings)} rule(s) triggered: {[f['rule_id'] for f in findings]}

Write one short opening sentence for the investigation report stating plainly that this
history has activity worth a closer look, without stating a conclusion about fraud.
"""
    text = gemini_client.generate_text(prompt, max_output_tokens=80)
    if text:
        return text, True
    return (
        f"This history has {len(findings)} rule trigger(s) worth a closer look; see findings below.",
        False,
    )


def build_report(customer_id, transactions, findings):
    needs_attention = len(findings) > 0
    overall_text, overall_used_llm = _overall_narrative(customer_id, findings)

    finding_reports = []
    any_llm_used = overall_used_llm
    for f in findings:
        narrative, used_llm = _narrative_for_finding(customer_id, f)
        any_llm_used = any_llm_used or used_llm
        finding_reports.append({
            "rule_id": f["rule_id"],
            "rule_title": f["rule_title"],
            "rule_text_cited": f["rule_text"],
            "transactions_involved": f["transactions_involved"],
            "evidence": f["evidence"],
            "deviation_explanation": f["deviation_explanation"],
            "investigator_narrative": narrative,
            "narrative_source": "gemini" if used_llm else "deterministic_template",
        })

    return {
        "customer_id": customer_id,
        "needs_attention": needs_attention,
        "summary": overall_text,
        "total_transactions_reviewed": len(transactions),
        "findings": finding_reports,
        "disclaimer": (
            "This report flags patterns for investigator review only. It does not "
            "conclude that fraud has occurred."
        ),
        "llm_used": any_llm_used,
    }
