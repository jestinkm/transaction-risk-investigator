import logging

from flask import Flask, jsonify, render_template

from src import config, data_loader, rules_engine, report_builder, gemini_client, ledger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = Flask(__name__, template_folder="frontend/templates", static_folder="frontend/static")

RULES = data_loader.load_rules()


@app.route("/")
def index():
    return render_template("index.html", llm_available=gemini_client.is_available())


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "llm_available": gemini_client.is_available()})


@app.route("/api/rules")
def api_rules():
    return jsonify(RULES)


@app.route("/api/customers")
def api_customers():
    return jsonify(data_loader.list_customers())


@app.route("/api/customers/<customer_id>/transactions")
def api_transactions(customer_id):
    txns = data_loader.load_transactions(customer_id)
    if txns is None:
        return jsonify({"error": f"unknown customer_id '{customer_id}'"}), 404
    return jsonify(txns)


@app.route("/api/investigate/<customer_id>", methods=["POST"])
def api_investigate(customer_id):
    txns = data_loader.load_transactions(customer_id)
    if txns is None:
        return jsonify({"error": f"unknown customer_id '{customer_id}'"}), 404
    if not txns:
        return jsonify({"error": "no transactions to evaluate"}), 400

    try:
        findings = rules_engine.evaluate(txns, RULES)
        report = report_builder.build_report(customer_id, txns, findings)
        ledger_entry = ledger.append_entry(customer_id, report)
        report["integrity"] = {
            "sealed": True,
            "ledger_index": ledger_entry["index"],
            "entry_hash": ledger_entry["entry_hash"],
            "timestamp": ledger_entry["timestamp"],
        }
        return jsonify(report)
    except Exception as e:
        logger.exception("investigation failed for %s", customer_id)
        return jsonify({
            "error": "investigation_failed",
            "message": str(e),
            "customer_id": customer_id,
        }), 500


@app.route("/api/ledger")
def api_ledger():
    return jsonify(ledger.get_chain())


@app.route("/api/ledger/verify")
def api_ledger_verify():
    return jsonify(ledger.verify_chain())


if __name__ == "__main__":
    app.run(host=config.HOST, port=config.PORT, debug=False)
