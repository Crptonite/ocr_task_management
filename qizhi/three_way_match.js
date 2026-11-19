/* ---------- Qizhi: 6b Part 2 — 3-Way Match, discrepancy tasks & department-head approval ---------- */
(function () {
  const BASE = "/api/three-way-match";
  const MAX_FILE = 10 * 1024 * 1024;
  const FILE_TYPES = ["application/pdf", "image/png", "image/jpeg"];
  const SEVERITY_PILL = { ok: "ok", low: "", medium: "review", high: "high", critical: "mismatch" };
  const STATUS_PILL = { open: "pending", in_progress: "review", awaiting_approval: "needs_attention", resolved: "ok" };
  const PRIORITY_PILL = { P1: "mismatch", P2: "high", P3: "review", P4: "" };

  const state = { invoice: null, users: [], tasks: [], selectedTask: null, busy: false, queue: [] };
  const el = (id) => document.getElementById(id);
  const pill = (cls, text) => `<span class="pill ${esc(cls)}">${esc(text)}</span>`;
  const words = (s) => String(s ?? "").replace(/_/g, " ");

  async function twmFetch(path, options = {}) {
    const headers = { "X-User": el("twm-user").value || "alex", ...options.headers };
    if (options.body && !(options.body instanceof FormData)) headers["Content-Type"] = "application/json";
    const res = await fetch((typeof API === "string" ? API : "") + BASE + path, { ...options, headers });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const detail = Array.isArray(body.detail)
        ? body.detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ")
        : body.detail;
      throw new Error(detail || res.statusText);
    }
    return res.json();
  }

  function showError(message) {
    const box = el("twm-error");
    box.hidden = !message;
    box.textContent = message || "";
  }

  /* ----- invoice + receipt input ----- */
  function selectInvoice(invoice, receiptText = "") {
    state.invoice = invoice;
    el("twm-receipt").value = receiptText;
    el("twm-run").disabled = false;
    showError("");
    const lines = invoice.lines
      .map((l) => `<tr><td>${esc(l.description)}${l.sku ? `<br /><span class="muted">${esc(l.sku)}</span>` : ""}</td>
        <td class="num">${esc(l.qty)}</td><td class="num">${esc(l.unit_price ?? "—")}</td></tr>`)
      .join("");
    el("twm-invoice").innerHTML = `
      <div class="twm-invoice-head">
        <strong>${esc(invoice.invoice_no)}</strong>
        <span class="muted">${esc(invoice.vendor || "No vendor")} · ${invoice.po_number ? esc(invoice.po_number) : "no PO number"} · ${esc(invoice.date || "no date")}</span>
      </div>
      <table class="table twm-table"><thead><tr><th>Item</th><th class="num">Qty</th><th class="num">Unit price</th></tr></thead>
      <tbody>${lines}</tbody></table>`;
  }

  function clearInput() {
    state.invoice = null;
    el("twm-receipt").value = "";
    el("twm-run").disabled = true;
    el("twm-queue-invoice").selectedIndex = 0;
    el("twm-invoice").innerHTML = `<p class="muted">No invoice selected. Pick a demo invoice or one from the review queue.</p>`;
    el("twm-result").innerHTML = `<p class="muted">No match run yet. Select an invoice and run the 3-way match.</p>`;
    el("twm-matrix-wrap").hidden = true;
    showError("");
  }

  async function uploadReceipt(file) {
    if (!file) return;
    if (!FILE_TYPES.includes(file.type)) return showError(`"${file.name}" is not a PDF, PNG or JPG file.`);
    if (file.size > MAX_FILE) return showError("The receipt is over 10 MB. Upload a smaller file.");
    const drop = el("twm-drop");
    drop.classList.add("twm-busy");
    showError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const out = await twmFetch("/receipts/extract", { method: "POST", body: form });
      el("twm-receipt").value = out.text;
      if (!out.parsed.items.length) showError("Text was read, but no receipt lines were recognised. Check and edit it below.");
    } catch (err) {
      showError(`Receipt extraction failed: ${err.message}`);
    } finally {
      drop.classList.remove("twm-busy");
      el("twm-file").value = "";
    }
  }

  /* ----- run + render the match ----- */
  async function runMatch() {
    if (!state.invoice || state.busy) return;
    state.busy = true;
    el("twm-run").disabled = true;
    showError("");
    try {
      const result = await twmFetch("/match", {
        method: "POST",
        body: JSON.stringify({ invoice: state.invoice, receipt_text: el("twm-receipt").value.trim() || null }),
      });
      renderResult(result);
      renderMatrix(result);
      await Promise.all([loadTasks(), loadAudit()]);
    } catch (err) {
      showError(`Match failed: ${err.message}`);
    } finally {
      state.busy = false;
      el("twm-run").disabled = !state.invoice;
    }
  }

  function renderResult(r) {
    const s = r.summary;
    const verdict = { MATCHED: ["matched", "Matched"], REVIEW: ["review", "Needs review"], BLOCKED: ["mismatch", "Blocked"] }[r.status];
    const notes = [];
    if (!r.po_found && r.po_number) notes.push(`PO ${r.po_number} was not found in the PO register.`);
    if (!r.po_number) notes.push("The invoice has no PO number.");
    if (!r.receipt_used) notes.push("No receipt supplied: only invoice vs PO was compared.");
    if (r.receipt && !r.receipt.ocr_trusted && r.receipt_used) notes.push("The receipt's own totals do not add up; OCR may have misread a figure.");
    notes.push(...(r.receipt_warnings || []));
    const issues = r.discrepancies
      .map((d) => `<li class="${d.severity === "critical" || d.severity === "high" ? "error" : "warning"}">${pill(SEVERITY_PILL[d.severity], d.severity)} ${esc(d.message)}</li>`)
      .join("");
    el("twm-result").innerHTML = `
      <h3>${esc(r.invoice_no)} ${pill(verdict[0], verdict[1])}</h3>
      <p class="muted">${esc(r.vendor || "No vendor")} · ${esc(r.po_number || "no PO")} · receipt ${r.receipt_used ? "included" : "not included"}</p>
      <div class="twm-summary">
        <div class="sum-card ${s.discrepancies ? "warn" : "ok"}"><span>Differences</span><strong>${s.discrepancies}</strong></div>
        <div class="sum-card ${s.critical ? "bad" : "ok"}"><span>Critical</span><strong>${s.critical}</strong></div>
        <div class="sum-card ${s.high ? "warn" : "ok"}"><span>High</span><strong>${s.high}</strong></div>
        <div class="sum-card"><span>Tasks</span><strong>${r.tasks.length}</strong></div>
      </div>
      ${notes.length ? `<ul>${notes.map((n) => `<li class="warning">${esc(n)}</li>`).join("")}</ul>` : ""}
      ${issues ? `<ul>${issues}</ul>` : `<p class="muted">All three documents agree. No tasks needed.</p>`}`;
  }

  function cellHtml(cell, qtyDiff, priceDiff) {
    if (!cell) return `<span class="muted">—</span>`;
    const derived = cell.derived ? ` <span class="muted" title="Derived from the printed line total">≈</span>` : "";
    return `<span class="${qtyDiff ? "twm-diff" : ""}">${esc(cell.qty)}</span> × <span class="${priceDiff ? "twm-diff" : ""}">${esc(cell.unit)}</span>${derived}`;
  }

  function renderMatrix(r) {
    el("twm-matrix-wrap").hidden = false;
    el("twm-matrix").innerHTML = r.matrix
      .map((row) => `<tr class="twm-row-${esc(row.status)}">
        <td><strong>${esc(row.key)}</strong><br /><span class="muted">${esc(row.description)}</span></td>
        <td class="num">${cellHtml(row.invoice)}</td>
        <td class="num">${cellHtml(row.po, row.diff.po_qty === "diff", row.diff.po_price === "diff")}</td>
        <td class="num">${cellHtml(row.receipt, row.diff.rc_qty === "diff", row.diff.rc_price === "diff")}</td>
        <td>${pill(SEVERITY_PILL[row.status], row.status === "ok" ? "Match" : row.status)}</td></tr>`)
      .join("");
    el("twm-checks").innerHTML = r.header_checks
      .map((h) => `<li>${pill(h.ok ? "ok" : "mismatch", h.ok ? "OK" : "Differs")} ${esc(h.label)}: <strong>${esc(h.invoice)}</strong> vs ${esc(h.other)}</li>`)
      .join("");
  }

  /* ----- tasks + approval ----- */
  async function loadTasks() {
    const out = await twmFetch("/tasks");
    state.tasks = out.tasks;
    const body = el("twm-tasks");
    if (!state.tasks.length) {
      body.innerHTML = `<tr><td colspan="4"><div class="twm-empty">No discrepancy tasks yet. Run a 3-way match on an invoice with differences.</div></td></tr>`;
    } else {
      body.innerHTML = state.tasks
        .map((t) => `<tr data-twm-task="${esc(t.id)}" class="${t.id === state.selectedTask ? "active" : ""}">
          <td><strong>${esc(t.title)}</strong><br /><span class="muted">${esc(t.invoice_no)} · ${esc(t.id)}</span></td>
          <td>${esc(t.department)}${t.assignee ? `<br /><span class="muted">${esc(t.assignee)}</span>` : ""}</td>
          <td>${pill(PRIORITY_PILL[t.priority], t.priority)}</td>
          <td>${pill(STATUS_PILL[t.status], words(t.status))}</td></tr>`)
        .join("");
    }
    if (state.selectedTask) await renderTaskDetail();
  }

  async function renderTaskDetail() {
    const t = state.tasks.find((x) => x.id === state.selectedTask);
    const box = el("twm-task-detail");
    if (!t) {
      state.selectedTask = null;
      box.innerHTML = `<p class="muted">No task selected. Choose a task to assign it, request approval or decide.</p>`;
      return;
    }
    const trail = await twmFetch(`/audit?task_id=${encodeURIComponent(t.id)}`).catch(() => []);
    const ap = t.approval;
    const canDecide = t.status === "awaiting_approval";
    const closed = t.status === "resolved";
    box.innerHTML = `
      <h3>${esc(t.title)}</h3>
      <p class="muted">${esc(t.invoice_no)} · ${esc(t.department)} · due ${esc(t.due)} · impact ${esc(t.impact)}</p>
      <p>${esc(t.description)}</p>
      <p><strong>Next step:</strong> ${esc(t.suggested_action)}${t.ai_refined ? ` <span class="muted">(AI-worded)</span>` : ""}</p>
      <p>${t.requires_approval ? pill("review", "Needs department-head approval") : pill("", "No approval needed")} ${pill(STATUS_PILL[t.status], words(t.status))}</p>
      ${ap ? `<ul><li class="${ap.decision === "rejected" ? "error" : "warning"}">Requested by ${esc(ap.requested_by)}: ${esc(ap.proposed_resolution)}
        ${ap.decision ? `<br />${esc(ap.decision)} by ${esc(ap.decided_by)}${ap.comment ? ` — ${esc(ap.comment)}` : ""}` : ""}</li></ul>` : ""}
      ${closed ? "" : `
      <label class="intake-text-label">${canDecide ? "Comment (required to reject)" : "Proposed resolution"}
        <textarea id="twm-note" rows="2" maxlength="500"></textarea></label>
      <div class="actions">
        ${canDecide
          ? `<button type="button" class="btn btn-accent btn-sm" data-twm-act="approved">Approve</button>
             <button type="button" class="btn btn-danger btn-sm" data-twm-act="rejected">Reject</button>`
          : `<button type="button" class="btn btn-outline btn-sm" data-twm-act="assign">Assign to me</button>
             <button type="button" class="btn btn-outline btn-sm" data-twm-act="in_progress">Start work</button>
             <button type="button" class="btn btn-outline btn-sm" data-twm-act="resolved">Mark resolved</button>
             <button type="button" class="btn btn-solid btn-sm" data-twm-act="request">Request approval</button>`}
      </div>`}
      <h4 class="twm-h">Task history</h4>
      ${trail.length ? `<ul>${trail.map((e) => `<li>#${e.seq} ${esc(e.action)} · ${esc(e.actor)}</li>`).join("")}</ul>` : `<p class="muted">No events yet.</p>`}`;
  }

  async function taskAction(act) {
    const t = state.tasks.find((x) => x.id === state.selectedTask);
    if (!t) return;
    const note = (el("twm-note")?.value || "").trim();
    const user = state.users.find((u) => u.id === el("twm-user").value);
    const id = encodeURIComponent(t.id);
    const call = {
      assign: () => twmFetch(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ assignee: user.name }) }),
      in_progress: () => twmFetch(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status: "in_progress" }) }),
      resolved: () => twmFetch(`/tasks/${id}`, { method: "PATCH", body: JSON.stringify({ status: "resolved" }) }),
      request: () => twmFetch(`/tasks/${id}/request-approval`, { method: "POST", body: JSON.stringify({ proposed_resolution: note }) }),
      approved: () => twmFetch(`/tasks/${id}/decision`, { method: "POST", body: JSON.stringify({ decision: "approved", comment: note }) }),
      rejected: () => twmFetch(`/tasks/${id}/decision`, { method: "POST", body: JSON.stringify({ decision: "rejected", comment: note }) }),
    }[act];
    try {
      await call();
      await Promise.all([loadTasks(), loadAudit()]);
    } catch (err) {
      await noticeModal("Action not allowed", err.message, "Approval rules");
    }
  }

  /* ----- audit trail ----- */
  async function loadAudit() {
    const events = await twmFetch("/audit");
    el("twm-audit").innerHTML = events.length
      ? events.slice(-30).reverse()
          .map((e) => `<tr><td>${e.seq}</td><td>${esc(new Date(e.ts).toLocaleString())}</td>
            <td>${esc(e.actor)}<br /><span class="muted">${esc(words(e.role))} · ${esc(e.department)}</span></td>
            <td>${esc(words(e.action))}</td><td>${esc(e.invoice_no || "—")}${e.task_id ? ` · ${esc(e.task_id)}` : ""}</td></tr>`)
          .join("")
      : `<tr><td colspan="5"><div class="twm-empty">The audit trail is empty. Every match, task change and approval is recorded here.</div></td></tr>`;
  }

  async function verifyAudit() {
    const out = el("twm-verify-status");
    try {
      const v = await twmFetch("/audit/verify");
      out.hidden = false;
      out.className = `pill ${v.valid ? "ok" : "mismatch"}`;
      out.textContent = v.valid ? `Chain intact · ${v.events} events` : `Tampering detected at event #${v.broken_at_seq}`;
    } catch (err) {
      showError(`Could not verify the audit trail: ${err.message}`);
    }
  }

  async function refreshQueue() {
    const sel = el("twm-queue-invoice");
    if (!sel) return [];
    const prevInvNo = sel.value !== "" ? state.queue[Number(sel.value)]?.invoice_no : null;
    const res = await fetch((typeof API === "string" ? API : "") + BASE + "/invoices");
    if (!res.ok) throw new Error(res.statusText);
    state.queue = await res.json();
    sel.innerHTML = `<option value="">Review queue invoice…</option>` +
      state.queue.map((i, n) => `<option value="${n}">${esc(i.invoice_no)} · ${esc(i.vendor)}</option>`).join("");
    if (prevInvNo) {
      const idx = state.queue.findIndex((i) => i.invoice_no === prevInvNo);
      if (idx >= 0) sel.value = String(idx);
    }
    return state.queue;
  }

  async function openInThreeWayMatch(invoiceNo) {
    if (!el("inv-3way")) return;
    await refreshQueue().catch(() => {});
    const idx = state.queue.findIndex((i) => i.invoice_no === invoiceNo);
    if (idx >= 0) {
      el("twm-queue-invoice").value = String(idx);
      selectInvoice(state.queue[idx]);
    }
    if (location.hash === "#invoices/three-way-match") {
      el("inv-3way")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      location.hash = "#invoices/three-way-match";
    }
  }

  window.refreshThreeWayQueue = refreshQueue;
  window.openInThreeWayMatch = openInThreeWayMatch;

  /* ----- start-up ----- */
  async function init() {
    const section = el("inv-3way");
    if (!section) return;
    try {
      const [users, scenarios] = await Promise.all([
        fetch((typeof API === "string" ? API : "") + BASE + "/users").then((r) => r.json()),
        fetch((typeof API === "string" ? API : "") + BASE + "/scenarios").then((r) => r.json()),
        refreshQueue(),
      ]);
      state.users = users;
      el("twm-user").innerHTML = users
        .map((u) => `<option value="${esc(u.id)}">${esc(u.name)} · ${u.role === "dept_head" ? `${esc(u.department)} head` : `${esc(u.department)} analyst`}</option>`)
        .join("");
      el("twm-scenarios").innerHTML = scenarios
        .map((s) => `<button type="button" class="chip" data-twm-scenario="${esc(s.id)}">${esc(s.label)}</button>`)
        .join("");

      el("twm-scenarios").addEventListener("click", (e) => {
        const btn = e.target.closest("[data-twm-scenario]");
        const s = btn && scenarios.find((x) => x.id === btn.dataset.twmScenario);
        if (!s) return;
        el("twm-queue-invoice").selectedIndex = 0;
        selectInvoice(s.invoice, s.receipt_text);
      });
      el("twm-queue-invoice").addEventListener("change", (e) => {
        if (e.target.value !== "") selectInvoice(state.queue[Number(e.target.value)]);
      });
      el("twm-user").addEventListener("change", () => renderTaskDetail());
      await Promise.all([loadTasks(), loadAudit()]);
    } catch (err) {
      showError("The 3-way match service is not reachable. Start the backend and reload the page.");
      el("twm-tasks").innerHTML = `<tr><td colspan="4" class="muted">Unavailable.</td></tr>`;
    }

    el("twm-run").addEventListener("click", runMatch);
    el("twm-clear").addEventListener("click", clearInput);
    el("twm-verify").addEventListener("click", verifyAudit);
    el("twm-file").addEventListener("change", (e) => uploadReceipt(e.target.files[0]));
    const drop = el("twm-drop");
    ["dragenter", "dragover"].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.add("drag"); }));
    ["dragleave", "drop"].forEach((n) => drop.addEventListener(n, (e) => { e.preventDefault(); drop.classList.remove("drag"); }));
    drop.addEventListener("drop", (e) => uploadReceipt(e.dataTransfer.files[0]));
    drop.addEventListener("click", (e) => { if (!e.target.closest("label")) el("twm-file").click(); });
    el("twm-tasks").addEventListener("click", (e) => {
      const row = e.target.closest("tr[data-twm-task]");
      if (!row) return;
      state.selectedTask = row.dataset.twmTask;
      loadTasks();
    });
    el("twm-task-detail").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-twm-act]");
      if (btn) taskAction(btn.dataset.twmAct);
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
