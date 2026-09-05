const customerSelect = document.getElementById("customerSelect");
const loadBtn = document.getElementById("loadBtn");
const investigateBtn = document.getElementById("investigateBtn");
const verifyBtn = document.getElementById("verifyBtn");
const spinner = document.getElementById("spinner");
const txnTableWrap = document.getElementById("txnTableWrap");
const reportWrap = document.getElementById("reportWrap");
const reportPanel = document.getElementById("reportPanel");
const ledgerWrap = document.getElementById("ledgerWrap");
const chainBadge = document.getElementById("chainBadge");

let currentCustomer = null;
let flaggedIds = new Set();

async function init() {
  const res = await fetch("/api/customers");
  const customers = await res.json();
  customerSelect.innerHTML = customers.map(c => `<option value="${c.id}">${c.label}</option>`).join("");
  await refreshLedger();
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, m => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
}

function renderTransactions(txns) {
  const rows = txns.map(t => `
    <tr class="${flaggedIds.has(t.txn_id) ? 'flagged' : ''}">
      <td>${t.txn_id}</td><td>${t.date}</td><td>${t.time}</td>
      <td>${escapeHtml(t.description)}</td><td>${t.amount.toFixed(2)}</td>
      <td>${t.channel}</td><td>${t.category}</td>
    </tr>`).join("");
  txnTableWrap.innerHTML = `
    <div class="table-scroll">
    <table>
      <thead><tr><th>ID</th><th>Date</th><th>Time</th><th>Description</th><th>Amount</th><th>Channel</th><th>Category</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    </div>`;
}

function renderReport(report) {
  const summaryClass = report.needs_attention ? "attention" : "clean";
  const icon = report.needs_attention ? "⚠️" : "✅";

  const findingsHtml = report.findings.map(f => `
    <div class="finding">
      <span class="source-tag">source: ${f.narrative_source}</span>
      <h3>${f.rule_title} <span class="rule-tag">${f.rule_id}</span></h3>
      <div class="rule-text">"${escapeHtml(f.rule_text_cited)}"</div>
      <p>${escapeHtml(f.investigator_narrative)}</p>
      <p><strong>Deviation:</strong> ${escapeHtml(f.deviation_explanation)}</p>
      <p class="txn-ids">Transactions: ${f.transactions_involved.join(", ")}</p>
    </div>`).join("");

  const integrityLine = report.integrity
    ? `<p class="hint small">🔒 Sealed to integrity ledger as entry #${report.integrity.ledger_index}
       (hash <code>${report.integrity.entry_hash.slice(0, 16)}&hellip;</code>)</p>`
    : "";

  reportWrap.innerHTML = `
    <div class="report-summary ${summaryClass}">
      <span class="status-icon">${icon}</span>
      <div>
        <strong>${report.needs_attention ? "Needs attention" : "Clean history"}</strong> &mdash; ${escapeHtml(report.summary)}
      </div>
    </div>
    ${findingsHtml || '<p class="hint">No findings.</p>'}
    <p class="hint">${escapeHtml(report.disclaimer)}</p>
    ${integrityLine}
  `;

  flaggedIds = new Set(report.findings.flatMap(f => f.transactions_involved));
  reportPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderLedger(entries) {
  if (!entries.length) {
    ledgerWrap.innerHTML = '<p class="hint">No reports sealed yet.</p>';
    return;
  }
  ledgerWrap.innerHTML = entries.slice().reverse().map(e => `
    <div class="ledger-entry">
      <span class="ledger-index">#${e.index}</span>
      <span class="ledger-customer">${e.customer_id}</span>
      <span class="ledger-hash">${e.entry_hash.slice(0, 20)}&hellip;</span>
    </div>`).join("");
}

async function refreshLedger() {
  const res = await fetch("/api/ledger");
  const entries = await res.json();
  renderLedger(entries);
  chainBadge.textContent = `⛓ ledger: ${entries.length} entr${entries.length === 1 ? "y" : "ies"}`;
  chainBadge.classList.remove("valid", "broken");
}

loadBtn.addEventListener("click", async () => {
  currentCustomer = customerSelect.value;
  flaggedIds = new Set();
  reportWrap.innerHTML = '<p class="hint">Run an investigation to see the report.</p>';
  const res = await fetch(`/api/customers/${currentCustomer}/transactions`);
  const txns = await res.json();
  renderTransactions(txns);
  investigateBtn.disabled = false;
});

investigateBtn.addEventListener("click", async () => {
  if (!currentCustomer) return;
  spinner.classList.remove("hidden");
  investigateBtn.disabled = true;
  reportWrap.innerHTML = '<p class="hint">Investigating&hellip;</p>';
  try {
    const res = await fetch(`/api/investigate/${currentCustomer}`, { method: "POST" });
    const report = await res.json();
    if (report.error) {
      reportWrap.innerHTML = `<p class="hint">Error: ${escapeHtml(report.message || report.error)}</p>`;
      return;
    }
    renderReport(report);
    const txnRes = await fetch(`/api/customers/${currentCustomer}/transactions`);
    renderTransactions(await txnRes.json());
    await refreshLedger();
  } finally {
    spinner.classList.add("hidden");
    investigateBtn.disabled = false;
  }
});

verifyBtn.addEventListener("click", async () => {
  verifyBtn.disabled = true;
  verifyBtn.textContent = "Verifying…";
  const res = await fetch("/api/ledger/verify");
  const result = await res.json();
  verifyBtn.disabled = false;
  verifyBtn.textContent = "Verify chain";

  chainBadge.classList.remove("valid", "broken");
  chainBadge.classList.add(result.valid ? "valid" : "broken");
  chainBadge.textContent = `⛓ ledger: ${result.length} entries`;

  const old = document.querySelector(".verify-result");
  if (old) old.remove();
  const div = document.createElement("div");
  div.className = `verify-result ${result.valid ? "valid" : "broken"}`;
  div.textContent = result.valid
    ? `✅ Chain verified — all ${result.length} sealed reports are intact, none altered.`
    : `⚠️ Chain integrity broken at entry #${result.broken_at} — a sealed report may have been tampered with.`;
  ledgerWrap.after(div);
});

init();
