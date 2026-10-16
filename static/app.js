const $ = (id) => document.getElementById(id);
const api = (path, opts = {}) => {
  const key = $("apiKey").value.trim();
  return fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", "X-API-Key": key, ...(opts.headers || {}) },
  }).then(async (r) => {
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail || r.statusText);
    return body;
  });
};
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmtNum = (v) => (typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined,{maximumFractionDigits:2})) : esc(v));

let lastAnswer = null;

// ---------- tabs ----------
document.querySelectorAll(".tab").forEach((t) => {
  t.onclick = () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.remove("on"));
    t.classList.add("on");
    ["ask","dash","schema"].forEach((k) => $("tab-"+k).classList.toggle("hidden", k !== t.dataset.tab));
    if (t.dataset.tab === "dash") loadDashboards();
    if (t.dataset.tab === "schema") loadSchema();
  };
});

// ---------- health / status ----------
api("/api/health").then((h) => {
  $("statusLine").textContent =
    `warehouse: ${h.warehouse} · language: ${h.llm_mode === "demo" ? "demo translator" : h.llm_mode} · read-only`;
  $("modeHint").textContent = h.warehouse === "demo"
    ? "Demo warehouse: 5 plants, 5 products, 80 quotes. Set DATABRICKS_HOST / HTTP_PATH / TOKEN to query your real tables — the UI doesn't change."
    : "Connected to Databricks. Questions run against your Unity Catalog tables.";
}).catch(() => { $("statusLine").textContent = "server unreachable"; });

// ---------- sample questions ----------
const SAMPLES = ["What tables can I use?", "Average price by product", "Revenue by product",
  "Quotes by plant", "Recent quotes", "How many quotes are accepted?"];
$("chips").innerHTML = SAMPLES.map((s) => `<button class="chip">${esc(s)}</button>`).join("");
document.querySelectorAll(".chip").forEach((c) => (c.onclick = () => { $("q").value = c.textContent; doAsk(); }));
$("q").addEventListener("keydown", (e) => { if (e.key === "Enter") doAsk(); });

// ---------- ask ----------
async function doAsk() {
  const question = $("q").value.trim();
  if (!question) return;
  const btn = $("askBtn");
  btn.disabled = true; btn.textContent = "Thinking…";
  try {
    const ans = await api("/api/ask", { method: "POST", body: JSON.stringify({ question }) });
    lastAnswer = ans;
    renderAnswer(ans, "answerCard", "ansQ", "ansExpl", "ansSql", "ansChart", "ansTable", "ansMeta");
    $("answerCard").classList.remove("hidden");
    $("saveBtn").style.display = ans.sql ? "" : "none";
  } catch (e) { alert("Ask failed: " + e.message); }
  btn.disabled = false; btn.textContent = "Ask →";
}
$("askBtn").onclick = doAsk;

function renderAnswer(ans, cardId, qId, explId, sqlId, chartId, tblId, metaId) {
  $(qId).textContent = "“" + ans.question + "”";
  $(explId).textContent = ans.explanation || "";
  $(sqlId).textContent = ans.sql || "-- no SQL (couldn't translate this one)";
  $(chartId).innerHTML = barChart(ans.columns, ans.rows);
  $(tblId).innerHTML = dataTable(ans.columns, ans.rows);
  $(metaId).textContent =
    `${ans.row_count} row${ans.row_count === 1 ? "" : "s"} · source: ${ans.source}` +
    (ans.llm_mode ? ` · language: ${ans.llm_mode}` : "");
}

function dataTable(cols, rows) {
  if (!cols.length) return `<tr><td style="color:var(--mut)">No rows.</td></tr>`;
  return `<thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>` +
    rows.map((r) => `<tr>${r.map((v) => `<td>${fmtNum(v)}</td>`).join("")}</tr>`).join("") +
    `</tbody>`;
}

// Auto bar chart: first column = label, first numeric column after it = value.
function barChart(cols, rows) {
  if (cols.length < 2 || !rows.length || rows.length > 30) return "";
  const vi = cols.findIndex((_, i) => i > 0 && rows.every((r) => typeof r[i] === "number"));
  if (vi < 1) return "";
  const max = Math.max(...rows.map((r) => Math.abs(r[vi])), 1e-9);
  return `<div class="bars">` + rows.slice(0, 12).map((r) => `
    <div class="brow"><span>${esc(r[0])}</span>
    <div class="track"><div class="fill" style="width:${(Math.abs(r[vi]) / max) * 100}%"></div></div>
    <span class="val">${fmtNum(r[vi])}</span></div>`).join("") + `</div>`;
}

// ---------- save to dashboard ----------
$("saveBtn").onclick = async () => {
  if (!lastAnswer || !lastAnswer.sql) return;
  const title = prompt("Dashboard card title:", lastAnswer.question);
  if (!title) return;
  await api("/api/dashboards", { method: "POST",
    body: JSON.stringify({ title, question: lastAnswer.question, sql: lastAnswer.sql }) });
  alert("Saved. Open the Dashboards tab to see it live.");
};

// ---------- dashboards ----------
async function loadDashboards() {
  const cards = await api("/api/dashboards").catch(() => []);
  $("dashGrid").innerHTML = cards.length ? cards.map((c) => `
    <div class="dcard">
      <h3>${esc(c.title)}</h3><p class="dq">${esc(c.question)}</p>
      ${c.result.error
        ? `<p class="hint">Error: ${esc(c.result.error)}</p>`
        : barChart(c.result.columns, c.result.rows) +
          `<div class="tblwrap"><table>${dataTable(c.result.columns, c.result.rows.slice(0, 8))}</table></div>`}
      <button class="del" onclick="delCard(${c.id})">remove</button>
    </div>`).join("")
    : `<p class="hint">Nothing here yet — ask a question, then “Save to dashboard”.</p>`;
}
async function delCard(id) {
  if (!confirm("Remove this card?")) return;
  await api(`/api/dashboards/${id}`, { method: "DELETE" });
  loadDashboards();
}

// ---------- schema explorer ----------
async function loadSchema() {
  const s = await api("/api/schema").catch(() => null);
  if (!s) return;
  $("schemaList").innerHTML = s.tables.map((t) => `
    <div class="schema-t">
      <div class="st-head">${esc(t.name)}<span>${t.rows != null ? t.rows + " rows" : ""}</span></div>
      <div class="st-cols">${t.columns.map((c) => `<code>${esc(c.name)}</code> <span style="font-size:11px">${esc(c.type)}</span>`).join(" · ")}</div>
    </div>`).join("");
}
