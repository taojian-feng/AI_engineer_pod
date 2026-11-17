"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (v) => (v === null || v === undefined ? "n/a" : Math.round(v * 100) + "%");
const store = {
  get(k, d) { try { const v = localStorage.getItem("podsim:" + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem("podsim:" + k, JSON.stringify(v)); } catch {} },
};

function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.remove("hidden"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.add("hidden"), 5000); }

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (r.status === 401 && !path.endsWith("/login")) { showLogin(); throw new Error("Please sign in."); }
  const raw = await r.text().catch(() => "");
  let data = {};
  try { data = raw ? JSON.parse(raw) : {}; } catch { data = {}; }
  if (!r.ok) {
    const d = data.detail;
    const body = raw && raw.length < 300 && !raw.trim().startsWith("<") ? ": " + raw.trim() : "";
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? d.map((x) => x.msg).join("; ") : "Request failed (HTTP " + r.status + ")" + body);
  }
  return data;
}

async function busy(btn, fn) {
  btn.disabled = true; btn.classList.add("spinner");
  try { return await fn(); } catch (e) { toast(e.message); } finally { btn.disabled = false; btn.classList.remove("spinner"); refreshUsage(); }
}

// Very small markdown renderer for exercise prompts (input is trusted, from our server, but still escaped).
function md(src) {
  const blocks = src.split(/```(?:\w+)?\n([\s\S]*?)```/g);
  return blocks.map((b, i) => {
    if (i % 2) return "<pre><code>" + esc(b) + "</code></pre>";
    return b.trim().split(/\n{2,}/).map((p) => {
      const inline = (t) => esc(t).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\*([^*]+)\*/g, "<i>$1</i>");
      const lines = p.split("\n");
      if (/^#{1,6} /.test(p)) return "<h4>" + inline(p.replace(/^#+ /, "")) + "</h4>";
      if (lines.every((l) => /^\s*[*-] /.test(l))) return "<ul>" + lines.map((l) => "<li>" + inline(l.replace(/^\s*[*-] /, "")) + "</li>").join("") + "</ul>";
      return "<p>" + inline(p).replace(/\n/g, "<br>") + "</p>";
    }).join("");
  }).join("");
}

// ------------------------------------------------------------------ auth & nav
function showLogin() { $("#login").classList.remove("hidden"); }
$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  try { await api("/api/login", { code: f.get("code") || "", name: f.get("name") || "" }); $("#login").classList.add("hidden"); boot(); }
  catch (err) { $("#login-error").textContent = err.message; }
});

function go(view) {
  $$(".view").forEach((v) => v.classList.add("hidden"));
  $("#view-" + view).classList.remove("hidden");
  $$("nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  $("#nav").classList.remove("open");
  location.hash = view;
  (onShow[view] || (() => {}))();
  window.scrollTo(0, 0);
}
$$("nav a").forEach((a) => a.addEventListener("click", () => go(a.dataset.view)));
document.addEventListener("click", (e) => { const g = e.target.closest("[data-goto]"); if (g) go(g.dataset.goto); });
$("#menu-btn").addEventListener("click", () => $("#nav").classList.toggle("open"));

async function refreshUsage() {
  try {
    const m = await api("/api/me");
    const mode = m.provider === "fake" ? " · offline demo mode" : "";
    $("#usage").textContent = `${m.name} · ${m.model} (${m.effort}) · ${Math.round(m.tokens_used / 1000)}k / ${Math.round(m.token_budget / 1000)}k tokens${mode}`;
    return m;
  } catch { return null; }
}

const onShow = {};

// ------------------------------------------------------------------ home
onShow.home = async () => {
  const rows = await api("/api/attempts").catch(() => []);
  if (!rows.length) return;
  $("#attempts").innerHTML = `<div class="tbl-wrap"><table class="tbl"><tr><th>When</th><th>Module</th><th>Detail</th><th>Score</th></tr>${rows.map((r) => `
    <tr><td>${new Date(r.ts * 1000).toLocaleString()}</td><td>${esc(r.module)}</td>
    <td class="small">${esc(Object.values(r.config).filter((v) => typeof v === "string" && v.length < 40).join(", ") || JSON.stringify(r.result).slice(0, 80))}</td>
    <td><b>${r.score}</b></td></tr>`).join("")}</table></div>`;
};

// ------------------------------------------------------------------ company
let company = null;
onShow.company = async () => {
  company = company || (await api("/api/company"));
  const tabs = ["Items", "Suppliers", "Open POs", ...Object.keys(company.docs)];
  $("#company-tabs").innerHTML = tabs.map((t, i) => `<button data-i="${i}" class="${i ? "" : "active"}">${esc(t.replace(".md", ""))}</button>`).join("");
  const show = (i) => {
    $$("#company-tabs button").forEach((b) => b.classList.toggle("active", +b.dataset.i === i));
    const t = tabs[i];
    let h = "";
    if (t === "Items") h = table(Object.entries(company.items).map(([k, v]) => ({ sku: k, ...v })));
    else if (t === "Suppliers") h = table(Object.entries(company.suppliers).map(([k, v]) => ({ id: k, ...v, supplies: v.supplies.join(", "), certifications: v.certifications.join(", ") })));
    else if (t === "Open POs") h = table(company.open_pos);
    else h = `<div class="md">${md(company.docs[t])}</div>`;
    $("#company-body").innerHTML = h;
  };
  $$("#company-tabs button").forEach((b) => b.addEventListener("click", () => show(+b.dataset.i)));
  show(0);
};
function table(rows) {
  if (!rows.length) return "<p class='muted'>None.</p>";
  const cols = Object.keys(rows[0]);
  return `<div class="tbl-wrap"><table class="tbl"><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>${rows.map((r) => `<tr>${cols.map((c) => `<td>${esc(r[c])}</td>`).join("")}</tr>`).join("")}</table></div>`;
}

// ------------------------------------------------------------------ RAG lab
let ragBaseline = null;
const RAG_FIELDS = ["chunk_size", "chunk_overlap", "top_k", "min_score", "split_on_headings", "system_prompt"];
function ragConfig() {
  const c = {};
  RAG_FIELDS.forEach((f) => { const el = $("#rag-" + f); c[f] = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value; });
  store.set("rag", c);
  return c;
}
function setRag(c) { RAG_FIELDS.forEach((f) => { const el = $("#rag-" + f); if (el.type === "checkbox") el.checked = !!c[f]; else el.value = c[f]; }); }
onShow.rag = async () => {
  if (!ragBaseline) { ragBaseline = await api("/api/rag/baseline"); setRag(store.get("rag", ragBaseline.config)); }
};
$("#rag-reset").addEventListener("click", () => { setRag(ragBaseline.config); ragConfig(); });
$("#rag-ask").addEventListener("click", (e) => busy(e.target, async () => {
  const q = $("#rag-q").value.trim(); if (!q) return;
  const r = await api("/api/rag/ask", { config: ragConfig(), question: q });
  $("#rag-answer").innerHTML = `<p style="white-space:pre-wrap">${esc(r.answer)}</p>
    <p class="muted small">${r.latency_ms} ms · ${r.tokens} tokens · <a data-trace="${r.trace_id}">view trace</a></p>
    <details><summary>${r.contexts.length} retrieved chunk(s)</summary>${r.contexts.map((c, i) => `<div class="ctx"><b>[${i + 1}] ${esc(c.id)}</b> (score ${c.score})<br>${esc(c.text)}</div>`).join("")}</details>`;
}));
$("#rag-q").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#rag-ask").click(); });
$("#rag-eval").addEventListener("click", (e) => busy(e.target, async () => {
  $("#rag-eval-out").innerHTML = "<p class='muted'>Running 16 cases… this takes about 30-60 seconds.</p>";
  const r = await api("/api/rag/eval", { config: ragConfig(), use_judge: $("#rag-judge").checked });
  const m = r.metrics;
  $("#rag-eval-out").innerHTML = `
    <div class="row-between"><div><span class="big-score">${r.score}</span> <span class="muted">/ 100</span></div><a data-trace="${r.trace_id}">view trace</a></div>
    <div class="metrics">
      ${metric("Accuracy", pct(m.accuracy))}${metric("Hallucination rate", pct(m.hallucination_rate))}
      ${metric("Groundedness", pct(m.groundedness))}${metric("Retrieval hit rate", pct(m.retrieval_hit_rate))}
      ${metric("Abstains when unanswerable", pct(m.abstention_on_unanswerable))}${metric("Citation rate", pct(m.citation_rate))}
      ${metric("p50 / p95 latency", `${m.p50_latency_ms} / ${m.p95_latency_ms} ms`)}${metric("Tokens", m.total_tokens.toLocaleString())}
    </div>
    <div class="tbl-wrap"><table class="tbl"><tr><th>Case</th><th>Question</th><th>Answer</th><th>Retrieved</th><th>Result</th></tr>
    ${r.rows.map((x) => `<tr><td>${x.id}${x.answerable ? "" : "<br><span class='muted small'>unanswerable</span>"}</td><td>${esc(x.question)}</td>
      <td class="small">${esc(x.answer).slice(0, 600)}${x.unsupported_claims.length ? `<br><span class="fail">Unsupported: ${esc(x.unsupported_claims.join("; "))}</span>` : ""}</td>
      <td class="small">${esc(x.retrieved.join(", "))}</td>
      <td>${x.correct ? "<span class='pass'>correct</span>" : "<span class='fail'>wrong</span>"}${x.hallucinated ? "<br><span class='fail'>hallucinated</span>" : ""}${x.retrieval_hit === false ? "<br><span class='fail'>retrieval miss</span>" : ""}</td></tr>`).join("")}
    </table></div>`;
}));
const metric = (label, val) => `<div class="metric"><b>${esc(val)}</b><span>${esc(label)}</span></div>`;

// ------------------------------------------------------------------ Agent lab
let agentBaseline = null;
function agentConfig() {
  const c = {
    system_prompt: $("#agent-system_prompt").value,
    max_steps: Number($("#agent-max_steps").value),
    memory_turns: Number($("#agent-memory_turns").value),
    tool_descriptions: Object.fromEntries($$("#agent-tools textarea").map((t) => [t.dataset.tool, t.value])),
  };
  store.set("agent", c);
  return c;
}
function setAgent(c) {
  $("#agent-system_prompt").value = c.system_prompt; $("#agent-max_steps").value = c.max_steps; $("#agent-memory_turns").value = c.memory_turns;
  $("#agent-tools").innerHTML = Object.entries(c.tool_descriptions).map(([k, v]) => `<label><code>${esc(k)}</code><textarea rows="2" data-tool="${esc(k)}">${esc(v)}</textarea></label>`).join("");
}
onShow.agent = async () => {
  if (agentBaseline) return;
  agentBaseline = await api("/api/agent/baseline");
  setAgent(store.get("agent", agentBaseline.config));
  $("#agent-scenarios").innerHTML = `<div class="tbl-wrap"><table class="tbl">${agentBaseline.scenarios.map((s) => `<tr><td><b>${s.id}</b></td><td>${esc(s.title)}</td><td class="small">${esc(s.prompt)}</td><td><button class="ghost small" data-run="${s.id}">Run</button></td></tr>`).join("")}</table></div>`;
  $$("#agent-scenarios [data-run]").forEach((b) => b.addEventListener("click", () => runAgentEval(b, [b.dataset.run])));
};
$("#agent-reset").addEventListener("click", () => { setAgent(agentBaseline.config); agentConfig(); });
function chatAdd(box, cls, html) { const d = document.createElement("div"); d.className = "msg " + cls; d.innerHTML = html; box.appendChild(d); box.scrollTop = box.scrollHeight; }
let agentReset = true;
$("#agent-new").addEventListener("click", () => { agentReset = true; $("#agent-chat").innerHTML = ""; chatAdd($("#agent-chat"), "sys", "New conversation. The ERP has been reset."); });
$("#agent-send").addEventListener("click", (e) => busy(e.target, async () => {
  const text = $("#agent-msg").value.trim(); if (!text) return;
  const box = $("#agent-chat"); chatAdd(box, "user", esc(text)); $("#agent-msg").value = "";
  const r = await api("/api/agent/chat", { config: agentConfig(), message: text, reset: agentReset });
  agentReset = false;
  r.tool_calls.forEach((t) => chatAdd(box, "tool", `${t.is_error ? "⚠ " : "→ "}${esc(t.name)}(${esc(JSON.stringify(t.input))})`));
  chatAdd(box, "bot", esc(r.reply) + `<div class="muted small">${r.steps} step(s) · <a data-trace="${r.trace_id}">trace</a></div>`);
}));
$("#agent-msg").addEventListener("keydown", (e) => { if (e.key === "Enter") $("#agent-send").click(); });
$("#agent-eval").addEventListener("click", (e) => runAgentEval(e.target, null));
function runAgentEval(btn, ids) {
  return busy(btn, async () => {
    $("#agent-eval-out").innerHTML = "<p class='muted'>Running scenarios against a fresh copy of the ERP…</p>";
    const r = await api("/api/agent/eval", { config: agentConfig(), scenario_ids: ids });
    const m = r.metrics;
    $("#agent-eval-out").innerHTML = `
      <div class="row-between"><div><span class="big-score">${r.score}</span> <span class="muted">/ 100${ids ? " (partial run, not saved)" : ""}</span></div><a data-trace="${r.trace_id}">view trace</a></div>
      <div class="metrics">${metric("Task success", pct(m.task_success_rate))}${metric("Checks passed", pct(m.check_pass_rate))}
        ${metric("Policy/check failures", m.policy_violations)}${metric("Halted at step limit", m.halted_runs)}
        ${metric("Avg steps", m.avg_steps)}${metric("Tool errors", m.tool_errors)}${metric("p50 latency", m.p50_latency_ms + " ms")}</div>
      ${r.rows.map((x) => `<details ${x.passed ? "" : "open"}><summary><span class="${x.passed ? "pass" : "fail"}">${x.passed ? "PASS" : "FAIL"}</span> ${x.id} · ${esc(x.title)} <span class="muted small">(${x.steps} steps)</span></summary>
        <ul>${x.checks.map((c) => `<li><span class="${c.passed ? "pass" : "fail"}">${c.passed ? "✓" : "✗"}</span> ${esc(c.name)} ${c.detail ? `<span class="muted small">(${esc(c.detail)})</span>` : ""}</li>`).join("")}</ul>
        <div class="small"><b>Tool calls:</b> ${x.tool_calls.map((t) => `<code>${esc(t.name)}</code>`).join(" → ") || "none"}</div>
        <div class="small" style="white-space:pre-wrap"><b>Final answer:</b> ${esc(x.final)}</div></details>`).join("")}`;
  });
}

// ------------------------------------------------------------------ Coding lab
let exercises = null, currentEx = null;
onShow.coding = async () => {
  if (exercises) return;
  exercises = await api("/api/coding/exercises");
  $("#coding-tabs").innerHTML = exercises.map((x, i) => `<button data-i="${i}">${esc(x.title)} <span class="muted small">${x.minutes}m</span></button>`).join("");
  $$("#coding-tabs button").forEach((b) => b.addEventListener("click", () => pickEx(+b.dataset.i)));
  pickEx(0);
};
function pickEx(i) {
  if (currentEx) store.set("code:" + currentEx.id, $("#coding-code").value);
  currentEx = exercises[i];
  $$("#coding-tabs button").forEach((b) => b.classList.toggle("active", +b.dataset.i === i));
  $("#coding-prompt").innerHTML = `<p class="chips"><span>${esc(currentEx.skill)}</span></p>` + md(currentEx.prompt);
  $("#coding-code").value = store.get("code:" + currentEx.id, currentEx.starter);
  $("#coding-out").innerHTML = "";
}
$("#coding-code").addEventListener("keydown", (e) => {
  if (e.key === "Tab") { e.preventDefault(); const t = e.target, s = t.selectionStart; t.setRangeText("    ", s, t.selectionEnd, "end"); }
});
$("#coding-code").addEventListener("input", () => store.set("code:" + currentEx.id, $("#coding-code").value));
$("#coding-reset").addEventListener("click", () => { $("#coding-code").value = currentEx.starter; store.set("code:" + currentEx.id, currentEx.starter); });
$("#coding-run").addEventListener("click", (e) => busy(e.target, async () => {
  const r = await api("/api/coding/run", { exercise_id: currentEx.id, code: $("#coding-code").value, feedback: $("#coding-fb").checked });
  $("#coding-out").innerHTML = `<p><span class="big-score">${r.passed}/${r.total}</span> tests passed <span class="muted small">(${r.backend} sandbox, ${r.duration_ms} ms)</span></p>
    ${r.harness_error ? `<p class="fail">${esc(r.harness_error)}</p>` : ""}
    <ul>${r.tests.map((t) => `<li><span class="${t.passed ? "pass" : "fail"}">${t.passed ? "✓" : "✗"}</span> <code>${esc(t.name)}</code> ${t.passed ? "" : `<span class="small">${esc(t.error)}</span>`}</li>`).join("")}</ul>
    ${r.stdout ? `<details><summary>stdout</summary><pre class="codeblock">${esc(r.stdout)}</pre></details>` : ""}
    ${r.stderr ? `<details><summary>stderr</summary><pre class="codeblock">${esc(r.stderr)}</pre></details>` : ""}
    ${r.feedback ? `<div class="card"><h3>Senior engineer feedback</h3><div style="white-space:pre-wrap">${esc(r.feedback)}</div></div>` : ""}`;
}));

// ------------------------------------------------------------------ Interview & stakeholder
let catalog = null;
async function loadCatalog() { catalog = catalog || (await api("/api/interview/catalog")); return catalog; }
onShow.interview = async () => {
  const c = await loadCatalog();
  if ($("#iv-track").options.length) return;
  $("#iv-track").innerHTML = Object.entries(c.tracks).map(([k, v]) => `<option value="${k}">${esc(v.title)}</option>`).join("");
  const desc = () => { const t = c.tracks[$("#iv-track").value]; $("#iv-jd").textContent = "JD: " + t.jd + "  ·  Rubric: " + t.rubric.join(", "); };
  $("#iv-track").addEventListener("change", desc); desc();
};
onShow.stakeholder = async () => {
  const c = await loadCatalog();
  if ($("#sh-persona").options.length) return;
  $("#sh-persona").innerHTML = Object.entries(c.personas).map(([k, v]) => `<option value="${k}">${esc(v.title)} (${esc(v.function)})</option>`).join("");
  const desc = () => { $("#sh-desc").textContent = c.personas[$("#sh-persona").value].persona; };
  $("#sh-persona").addEventListener("change", desc); desc();
};

function conversation(prefix, startPath, getTopic, extra, labels) {
  let convId = null, answered = false, starting = false;
  const box = $(`#${prefix}-chat`);
  const startBtn = $(`#${prefix}-start`);
  const fail = (e) => chatAdd(box, "err", esc("Couldn't get a reply: " + e.message));
  async function start() {
    if (starting) return;
    starting = true; startBtn.disabled = true; startBtn.classList.add("spinner");
    convId = null; answered = false;
    box.innerHTML = ""; $(`#${prefix}-score`).innerHTML = "";
    chatAdd(box, "sys", esc(labels.waiting));
    try {
      const r = await api(startPath, { topic: getTopic(), ...(extra ? extra() : {}) });
      box.innerHTML = "";
      convId = r.id; chatAdd(box, "bot", esc(r.message));
      $(`#${prefix}-msg`).focus();
    } catch (e) {
      box.innerHTML = ""; fail(e);
    } finally {
      starting = false; startBtn.disabled = false; startBtn.classList.remove("spinner"); refreshUsage();
    }
  }
  chatAdd(box, "sys", esc(labels.idle));
  startBtn.addEventListener("click", start);
  // Picking a topic starts the conversation, unless the candidate is mid-way through one.
  $(`#${prefix}-${labels.select}`).addEventListener("change", () => {
    if (answered) chatAdd(box, "sys", esc(labels.changed));
    else start();
  });
  $(`#${prefix}-send`).addEventListener("click", (e) => busy(e.target, async () => {
    if (!convId) return toast(labels.notStarted);
    const text = $(`#${prefix}-msg`).value.trim(); if (!text) return;
    chatAdd(box, "user", esc(text)); $(`#${prefix}-msg`).value = "";
    try {
      const r = await api("/api/conversation/reply", { id: convId, text });
      answered = true; chatAdd(box, "bot", esc(r.message));
    } catch (e) {
      $(`#${prefix}-msg`).value = text; fail(e);
    }
  }));
  $(`#${prefix}-msg`).addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) $(`#${prefix}-send`).click(); });
  $(`#${prefix}-finish`).addEventListener("click", (e) => busy(e.target, async () => {
    if (!convId) return toast(labels.notStarted);
    try {
      const r = await api("/api/conversation/finish", { id: convId });
      $(`#${prefix}-score`).innerHTML = scorecard(r.scorecard);
    } catch (e) { fail(e); }
  }));
}
function scorecard(s) {
  return `<div class="card"><div class="row-between"><h3>Scorecard</h3><div><span class="big-score">${Number(s.overall).toFixed(1)}</span><span class="muted"> / 5 · ${esc(s.recommendation)}</span></div></div>
    <div class="tbl-wrap"><table class="tbl"><tr><th>Criterion</th><th>Score</th><th>Evidence</th><th>How to improve</th></tr>
    ${s.criteria.map((c) => `<tr><td>${esc(c.criterion)}</td><td><b>${c.score}</b>/5</td><td class="small">${esc(c.evidence)}</td><td class="small">${esc(c.improvement)}</td></tr>`).join("")}</table></div>
    ${s.facts_uncovered ? `<div class="grid2" style="margin-top:12px"><div><h3 class="pass">Facts you uncovered (${s.facts_uncovered.length})</h3><ul>${s.facts_uncovered.map((f) => `<li>${esc(f)}</li>`).join("")}</ul></div>
      <div><h3 class="fail">Facts you missed (${s.facts_missed.length})</h3><ul>${s.facts_missed.map((f) => `<li>${esc(f)}</li>`).join("")}</ul></div></div>` : ""}
    <div class="grid2" style="margin-top:12px"><div><h3>Strengths</h3><ul>${s.strengths.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
    <div><h3>Improvements</h3><ul>${s.improvements.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div></div>
    <h3>What a strong answer covers</h3><p style="white-space:pre-wrap">${esc(s.model_answer)}</p></div>`;
}
conversation("iv", "/api/interview/start", () => $("#iv-track").value, () => ({ coach: $("#iv-coach").checked }), {
  select: "track",
  idle: "Pick a track (or click Start interview) and the interviewer will introduce themselves and ask the first question.",
  waiting: "The interviewer is joining the call and preparing the first question…",
  changed: "Track changed. Click Start interview to restart with the new track (this ends the current interview).",
  notStarted: "Start the interview first.",
});
conversation("sh", "/api/stakeholder/start", () => $("#sh-persona").value, null, {
  select: "persona",
  idle: "Pick a stakeholder (or click Walk into the meeting) to begin.",
  waiting: "Walking into the meeting…",
  changed: "Stakeholder changed. Click Walk into the meeting to start over with them.",
  notStarted: "Start the meeting first.",
});

// ------------------------------------------------------------------ Code review
let currentReview = null;
onShow.review = async () => {
  const c = await loadCatalog();
  if ($("#review-tabs").children.length) return;
  const ids = Object.keys(c.reviews);
  $("#review-tabs").innerHTML = ids.map((k) => `<button data-k="${k}">${esc(c.reviews[k].title.replace("Review: ", ""))}</button>`).join("");
  const pick = (k) => {
    currentReview = k;
    $$("#review-tabs button").forEach((b) => b.classList.toggle("active", b.dataset.k === k));
    $("#review-context").textContent = c.reviews[k].context; $("#review-code").textContent = c.reviews[k].code;
    $("#review-text").value = store.get("review:" + k, ""); $("#review-out").innerHTML = "";
  };
  $$("#review-tabs button").forEach((b) => b.addEventListener("click", () => pick(b.dataset.k)));
  pick(ids[0]);
};
$("#review-text").addEventListener("input", () => store.set("review:" + currentReview, $("#review-text").value));
$("#review-grade").addEventListener("click", (e) => busy(e.target, async () => {
  const g = await api("/api/review/grade", { review_id: currentReview, text: $("#review-text").value });
  const list = (t, xs, cls) => xs.length ? `<h3 class="${cls || ""}">${t} (${xs.length})</h3><ul>${xs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  $("#review-out").innerHTML = `<p><span class="big-score">${g.score}</span> / 100</p><p style="white-space:pre-wrap">${esc(g.feedback)}</p>
    ${list("Issues you caught", g.issues_found, "pass")}${list("Issues you missed", g.issues_missed, "fail")}
    ${list("Other good points", g.valid_extra_points)}${list("Incorrect claims", g.incorrect_claims, "fail")}`;
}));

// ------------------------------------------------------------------ Traces
onShow.traces = async () => {
  const rows = await api("/api/traces");
  $("#traces-list").innerHTML = rows.length ? `<div class="tbl-wrap"><table class="tbl"><tr><th>Time</th><th>Kinds</th><th>Spans</th><th>Tokens</th><th>Errors</th></tr>
    ${rows.map((t) => `<tr><td><a data-trace="${t.trace_id}">${new Date(t.ts * 1000).toLocaleTimeString()}</a></td><td class="small">${esc(t.kinds)}</td><td>${t.spans}</td><td>${t.tokens || 0}</td><td>${t.errors ? `<span class="fail">${t.errors}</span>` : 0}</td></tr>`).join("")}</table></div>` : "<p class='muted'>No traces yet.</p>";
};
$("#traces-refresh").addEventListener("click", () => onShow.traces());
async function showTrace(id) {
  go("traces");
  const spans = await api("/api/traces/" + id);
  $("#trace-detail").innerHTML = spans.map((s) => `<details><summary><code>${esc(s.kind)}</code> ${esc(s.name)} · ${Math.round(s.latency_ms)} ms${s.input_tokens + s.output_tokens ? ` · ${s.input_tokens}+${s.output_tokens} tok` : ""}${s.error ? ` <span class="fail">${esc(s.error)}</span>` : ""}</summary>
    <div class="small"><b>input</b><pre class="codeblock">${esc(pretty(s.input))}</pre><b>output</b><pre class="codeblock">${esc(pretty(s.output))}</pre></div></details>`).join("");
}
const pretty = (s) => { try { return JSON.stringify(JSON.parse(s), null, 2); } catch { return s; } };
document.addEventListener("click", (e) => { const t = e.target.closest("[data-trace]"); if (t) { e.preventDefault(); showTrace(t.dataset.trace); } });

// ------------------------------------------------------------------ boot
async function boot() {
  const m = await refreshUsage();
  if (!m) return;
  const v = location.hash.slice(1);
  go($("#view-" + v) ? v : "home");
}
(async () => {
  const cfg = await api("/api/config").catch(() => ({ access_code_required: true }));
  if (!cfg.access_code_required) $("#code-label").classList.add("hidden");
  boot();
})();
