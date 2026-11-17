/* ---------- Aeric: 6a PO Intake & Validation ---------- */

let intakeSamples = [];
let intakeResult = null;
let intakeFile = null;
let intakeSourceLabel = "manual entry";
let intakeTimer = null;

const INTAKE_FIELDS = ["po_number", "buyer", "buyer_email", "port", "order_date", "delivery_date", "currency"];

function collectIntakePayload() {
  const po = {};
  INTAKE_FIELDS.forEach((key) => {
    const el = $(`[data-po-field="${key}"]`);
    const v = el ? el.value.trim() : "";
    po[key] = v ? (key === "currency" ? v.toUpperCase() : v) : null;
  });
  po.lines = $$("#intake-line-rows tr").map((tr) => {
    const qRaw = $('[name="quantity"]', tr).value.trim();
    const pRaw = $('[name="unit_price"]', tr).value.trim();
    return {
      sku: $('[name="sku"]', tr).value.trim().toUpperCase() || null,
      description: $('[name="description"]', tr).value.trim() || null,
      quantity: qRaw === "" ? null : Number(qRaw),
      unit_price: pRaw === "" ? null : Number(pRaw),
    };
  });
  return po;
}

function matchBadgeLabel(m) {
  if (!m) return "";
  const pct = m.confidence ? ` ${Math.round(m.confidence * 100)}%` : "";
  if (m.status === "exact") return `Exact match · 100%`;
  if (m.status === "typo") return `1-char typo${pct}`;
  if (m.status === "near") return `Near match${pct}`;
  if (m.status === "missing") return "Missing SKU";
  return "Unknown SKU";
}

function renderIntake(res) {
  intakeResult = res;
  $("#intake-empty").hidden = true;
  $("#intake-workspace").hidden = false;

  const pill = $("#intake-status-pill");
  pill.hidden = false;
  pill.className = `pill ${res.status}`;
  pill.textContent = label(res.status);

  if (res.meta) {
    const m = res.meta;
    const tokLabel = m.ai_used ? `AI tokens: ${m.tokens}` : "0 AI tokens (rules)";
    $("#intake-meta-line").textContent =
      `Source: ${m.source} · Parser: ${m.method} · ${tokLabel} · ${m.elapsed_ms} ms`;
  }

  const s = res.summary || {};
  const cur = res.po?.currency || "USD";
  $("#intake-summary").innerHTML = `
    <div class="sum-card"><span>SKUs Matched</span><strong>${s.exact ?? 0} / ${s.lines ?? 0}</strong></div>
    <div class="sum-card ${(s.sku_flags || 0) > 0 ? "bad" : "ok"}"><span>SKU Flags</span><strong>${s.sku_flags ?? 0}</strong></div>
    <div class="sum-card ${(s.errors || 0) > 0 ? "bad" : "ok"}"><span>Blocking Errors</span><strong>${s.errors ?? 0}</strong></div>
    <div class="sum-card"><span>PO Total</span><strong>${money(s.total ?? 0, cur)}</strong></div>
  `;

  // Issues & parser warning banner
  const alertsEl = $("#intake-alerts");
  const issues = res.issues || [];
  const metaNote = res.meta?.note;
  if (issues.length || metaNote) {
    alertsEl.hidden = false;
    alertsEl.className = `intake-alerts ${issues.some((i) => i.level === "error") ? "has-errors" : ""}`;
    alertsEl.innerHTML =
      (metaNote ? `<p class="warn"><strong>Note:</strong> ${esc(metaNote)}</p>` : "") +
      (issues.length
        ? `<ul>${issues.map((i) => `<li class="${i.level === "error" ? "err" : "warn"}">${esc(i.message)}</li>`).join("")}</ul>`
        : "");
  } else {
    alertsEl.hidden = true;
    alertsEl.innerHTML = "";
  }

  // Header inputs + field validation highlights
  const po = res.po || {};
  const fields = res.fields || {};
  INTAKE_FIELDS.forEach((key) => {
    const input = $(`[data-po-field="${key}"]`);
    const group = $(`#intake-fields [data-field="${key}"]`);
    const msgEl = $(`#intake-fields [data-msg="${key}"]`);
    if (input) input.value = po[key] ?? "";
    const f = fields[key] || { state: "ok", message: "" };
    if (group) {
      group.classList.remove("field-error", "field-warn", "field-ok");
      if (f.state === "missing" || f.state === "invalid") group.classList.add("field-error");
      else if (f.state === "warning") group.classList.add("field-warn");
      else group.classList.add("field-ok");
    }
    if (msgEl) msgEl.textContent = f.message || "";
  });

  // Editable line items table + Fuzzy SKU match + 1-click Accept suggestion
  const lines = res.lines || [];
  const tbody = $("#intake-line-rows");
  tbody.innerHTML = lines.length
    ? lines
        .map((line, idx) => {
          const m = line.match || { status: "unknown" };
          const hasErr = (line.problems || []).some((p) => p.level === "error");
          const canAccept = m.suggested_sku && m.status !== "exact";
          const hint = m.message || (m.suggested_name ? m.suggested_name : "");
          return `<tr data-line-idx="${idx}" class="${hasErr ? "row-bad" : ""}">
            <td>${idx + 1}</td>
            <td><input name="sku" value="${esc(line.sku || "")}" placeholder="e.g. KD-CH-2047" maxlength="40" aria-label="SKU line ${idx + 1}" /></td>
            <td>
              <div class="sku-match-cell">
                <span class="match-chip ${esc(m.status)}">${esc(matchBadgeLabel(m))}</span>
                ${hint ? `<span class="match-hint">${esc(hint)}</span>` : ""}
                ${canAccept ? `<button type="button" class="btn-accept-sku" data-accept-sku="${esc(m.suggested_sku)}" data-accept-name="${esc(m.suggested_name || "")}" data-accept-price="${m.list_price ?? ""}">Accept ${esc(m.suggested_sku)}</button>` : ""}
              </div>
            </td>
            <td><input name="description" value="${esc(line.description || "")}" list="catalog-names" placeholder="Item description" maxlength="200" aria-label="Description line ${idx + 1}" /></td>
            <td><input name="quantity" type="number" min="0" step="1" value="${line.quantity ?? ""}" aria-label="Quantity line ${idx + 1}" /></td>
            <td><input name="unit_price" type="number" min="0" step="0.01" value="${line.unit_price ?? ""}" aria-label="Unit price line ${idx + 1}" /></td>
            <td class="num">${line.amount == null ? "—" : Number(line.amount).toFixed(2)}</td>
            <td><button type="button" class="icon-btn link" data-remove-line="${idx}" title="Remove line" aria-label="Remove line ${idx + 1}">✕</button></td>
          </tr>`;
        })
        .join("")
    : `<tr><td colspan="8" class="muted">No line items yet. Click "+ Add SKU Line" below.</td></tr>`;

  const blockerEl = $("#intake-blocker");
  const submitBtn = $("#intake-submit-btn");
  submitBtn.disabled = !res.can_submit;
  if (res.can_submit) {
    blockerEl.className = "intake-blocker ready";
    blockerEl.textContent = "All required fields & SKUs verified — ready to queue.";
  } else {
    blockerEl.className = "intake-blocker blocked";
    blockerEl.textContent = `${s.errors || 1} blocking error(s) must be fixed before sending to Order Queue.`;
  }
}

async function revalidateIntake() {
  if (!intakeResult) return;
  const payload = collectIntakePayload();
  const prevMeta = intakeResult.meta;
  const res = await api("/api/po-intake/validate", { method: "POST", body: JSON.stringify(payload) });
  res.meta = prevMeta;
  renderIntake(res);
}

function scheduleIntakeValidate() {
  clearTimeout(intakeTimer);
  intakeTimer = setTimeout(() => {
    revalidateIntake().catch(() => {});
  }, 240);
}

async function parseIntakeSource({ file = null, text = null, labelText = "pasted text" } = {}) {
  const parseBtn = $("#intake-parse-btn");
  const hint = $("#intake-parse-hint");
  parseBtn.disabled = true;
  parseBtn.textContent = "Parsing...";
  if (hint) hint.textContent = "Running hybrid parser & catalog check...";
  try {
    const fd = new FormData();
    if (file) fd.append("file", file);
    else fd.append("text", text || "");
    const res = await api("/api/po-intake", { method: "POST", body: fd });
    intakeSourceLabel = file ? file.name : labelText;
    renderIntake(res);
    if (hint) hint.textContent = res.meta?.ai_used ? `Parsed with AI (${res.meta.tokens} tokens).` : "Parsed cleanly via deterministic rules (0 tokens).";
  } catch (err) {
    await noticeModal("PO Intake Failed", err.message, "Upload / Parse Error");
    if (hint) hint.textContent = err.message;
  } finally {
    parseBtn.disabled = false;
    parseBtn.textContent = "Extract & Validate";
  }
}

async function loadIntakeSamples() {
  if (intakeSamples.length) return;
  intakeSamples = await api("/api/po-intake/samples");
  const wrap = $("#intake-sample-chips");
  if (!wrap) return;
  wrap.innerHTML = intakeSamples
    .map((s) => `<button type="button" class="chip" data-sample="${esc(s.id)}" title="${esc(s.hint)}">${esc(s.label)}</button>`)
    .join("");
  $$("[data-sample]", wrap).forEach((btn) =>
    btn.addEventListener("click", () => {
      const sample = intakeSamples.find((x) => x.id === btn.dataset.sample);
      if (!sample) return;
      $$(".chip", wrap).forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      intakeFile = null;
      if ($("#intake-file")) $("#intake-file").value = "";
      $("#intake-file-name").textContent = "Drop a PO file here or click to browse";
      $("#intake-raw-text").value = sample.text;
      parseIntakeSource({ text: sample.text, labelText: sample.label });
    })
  );
}

function wireIntakeEvents() {
  const dz = $("#intake-dropzone");
  const fileIn = $("#intake-file");
  const browseBtn = $("#intake-browse-btn");
  if (!dz || dz.dataset.wired) return;
  dz.dataset.wired = "1";

  const pickFile = (file) => {
    if (!file) return;
    const allowed = /\.(pdf|csv|txt|png|jpe?g|webp)$/i;
    if (!allowed.test(file.name)) {
      noticeModal("Unsupported File", "Please upload a PDF, CSV, TXT, PNG, JPG, or WEBP purchase order.", "File Type Error");
      return;
    }
    intakeFile = file;
    $("#intake-file-name").textContent = file.name;
    $$("#intake-sample-chips .chip").forEach((c) => c.classList.remove("active"));
    parseIntakeSource({ file });
  };

  browseBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    fileIn.click();
  });
  dz.addEventListener("click", () => fileIn.click());
  dz.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileIn.click();
    }
  });
  fileIn.addEventListener("change", () => pickFile(fileIn.files[0]));
  ["dragover", "dragleave", "drop"].forEach((evt) =>
    dz.addEventListener(evt, (e) => {
      e.preventDefault();
      dz.classList.toggle("drag", evt === "dragover");
      if (evt === "drop" && e.dataTransfer.files[0]) pickFile(e.dataTransfer.files[0]);
    })
  );

  $("#intake-parse-btn")?.addEventListener("click", () => {
    const text = $("#intake-raw-text").value.trim();
    if (!text && intakeFile) {
      parseIntakeSource({ file: intakeFile });
      return;
    }
    if (!text) {
      noticeModal("Nothing to Parse", "Upload a PO file, paste PO text, or choose one of the test samples first.", "Input Required");
      return;
    }
    intakeFile = null;
    parseIntakeSource({ text });
  });

  $("#intake-blank-btn")?.addEventListener("click", async () => {
    intakeFile = null;
    $("#intake-file").value = "";
    $("#intake-file-name").textContent = "Drop a PO file here or click to browse";
    $("#intake-raw-text").value = "";
    intakeSourceLabel = "blank form";
    const blank = { po_number: null, buyer: null, buyer_email: null, port: null, order_date: new Date().toISOString().slice(0, 10), delivery_date: null, currency: "USD", lines: [{ sku: "", description: "", quantity: 1, unit_price: 0 }] };
    const res = await api("/api/po-intake/validate", { method: "POST", body: JSON.stringify(blank) });
    res.meta = { source: "blank PO", method: "manual", ai_used: false, tokens: 0, elapsed_ms: 0 };
    renderIntake(res);
  });

  $("#intake-reset-btn")?.addEventListener("click", () => {
    intakeResult = null;
    intakeFile = null;
    if ($("#intake-file")) $("#intake-file").value = "";
    $("#intake-file-name").textContent = "Drop a PO file here or click to browse";
    $("#intake-raw-text").value = "";
    $("#intake-workspace").hidden = true;
    $("#intake-empty").hidden = false;
    $("#intake-status-pill").hidden = true;
    $("#intake-meta-line").textContent = "Load a sample, upload a file, or start a blank PO to inspect.";
    $("#intake-parse-hint").textContent = "Rules parse structured POs with 0 AI tokens.";
    $$("#intake-sample-chips .chip").forEach((c) => c.classList.remove("active"));
  });

  // Live header re-validation
  $("#intake-fields")?.addEventListener("input", scheduleIntakeValidate);
  $("#intake-fields")?.addEventListener("change", () => revalidateIntake().catch(() => {}));

  // Inline line editing, catalog autocomplete, 1-click Accept Suggested SKU, remove line
  const lineBody = $("#intake-line-rows");
  lineBody?.addEventListener("input", (e) => {
    const tr = e.target.closest("tr");
    if (!tr) return;
    if (e.target.name === "description") {
      const hit = catalog.find((c) => c.name.toLowerCase() === e.target.value.trim().toLowerCase());
      if (hit) {
        $('[name="sku"]', tr).value = hit.sku;
        if (!$('[name="unit_price"]', tr).value) $('[name="unit_price"]', tr).value = hit.unit_price;
      }
    }
    scheduleIntakeValidate();
  });
  lineBody?.addEventListener("click", async (e) => {
    const acceptBtn = e.target.closest("[data-accept-sku]");
    if (acceptBtn) {
      const tr = acceptBtn.closest("tr");
      $('[name="sku"]', tr).value = acceptBtn.dataset.acceptSku;
      if (!$('[name="description"]', tr).value.trim() && acceptBtn.dataset.acceptName) {
        $('[name="description"]', tr).value = acceptBtn.dataset.acceptName;
      }
      if ((!$('[name="unit_price"]', tr).value || Number($('[name="unit_price"]', tr).value) === 0) && acceptBtn.dataset.acceptPrice) {
        $('[name="unit_price"]', tr).value = acceptBtn.dataset.acceptPrice;
      }
      await revalidateIntake().catch(() => {});
      return;
    }
    const rmBtn = e.target.closest("[data-remove-line]");
    if (rmBtn) {
      rmBtn.closest("tr")?.remove();
      await revalidateIntake().catch(() => {});
    }
  });

  $("#intake-add-line")?.addEventListener("click", async () => {
    if (!intakeResult) return;
    const payload = collectIntakePayload();
    payload.lines.push({ sku: null, description: null, quantity: 1, unit_price: 0 });
    const prevMeta = intakeResult.meta;
    const res = await api("/api/po-intake/validate", { method: "POST", body: JSON.stringify(payload) });
    res.meta = prevMeta;
    renderIntake(res);
  });

  // 1-Click AI Buyer Clarification Email modal
  const updateMailto = () => {
    const to = encodeURIComponent($("#po-email-to").value.trim());
    const sub = encodeURIComponent($("#po-email-subject").value);
    const body = encodeURIComponent($("#po-email-body").value);
    $("#po-email-mailto").href = `mailto:${to}?subject=${sub}&body=${body}`;
  };
  ["#po-email-to", "#po-email-subject", "#po-email-body"].forEach((sel) =>
    $(sel)?.addEventListener("input", updateMailto)
  );
  $("#po-email-close")?.addEventListener("click", () => ($("#po-email-modal").hidden = true));
  $("#po-email-modal")?.addEventListener("click", (e) => {
    if (e.target.id === "po-email-modal") $("#po-email-modal").hidden = true;
  });
  $("#po-email-copy")?.addEventListener("click", async () => {
    const copyBtn = $("#po-email-copy");
    const full = `To: ${$("#po-email-to").value}\nSubject: ${$("#po-email-subject").value}\n\n${$("#po-email-body").value}`;
    try {
      await navigator.clipboard.writeText(full);
      copyBtn.textContent = "Copied";
      setTimeout(() => (copyBtn.textContent = "Copy Email"), 1600);
    } catch {
      $("#po-email-body").select();
    }
  });

  $("#intake-email-btn")?.addEventListener("click", async () => {
    const payload = collectIntakePayload();
    const btn = $("#intake-email-btn");
    btn.disabled = true;
    btn.textContent = "Drafting...";
    try {
      const draft = await api("/api/po-intake/email", { method: "POST", body: JSON.stringify(payload) });
      $("#po-email-to").value = draft.to || "";
      $("#po-email-subject").value = draft.subject || "";
      $("#po-email-body").value = draft.body || "";
      $("#po-email-mailto").href = draft.mailto || "#";
      const srcBadge = $("#po-email-source");
      srcBadge.textContent = draft.generator === "ai" ? "AI Polished" : "Deterministic Template";
      srcBadge.className = `pill ${draft.generator === "ai" ? "generated" : "ready"}`;
      $("#po-email-modal").hidden = false;
    } catch (err) {
      await noticeModal("Email Draft Failed", err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Draft Buyer Clarification Email";
    }
  });

  $("#intake-submit-btn")?.addEventListener("click", async () => {
    const payload = collectIntakePayload();
    const by = (adminInput?.value || "").trim() || "Order desk";
    const btn = $("#intake-submit-btn");
    btn.disabled = true;
    btn.textContent = "Sending...";
    try {
      const out = await api("/api/po-intake/submit", {
        method: "POST",
        body: JSON.stringify({ ...payload, created_by: by, source: intakeSourceLabel }),
      });
      selectedOrderId = out.order.id;
      await loadOrders();
      await noticeModal("PO Queued", `${out.order.order_number} has been validated and added to the Order Queue (${out.order.id}).`, "Sent to Queue");
    } catch (err) {
      await noticeModal("Cannot Queue PO", err.message, "Validation Error");
    } finally {
      btn.textContent = "Send to Order Queue";
      if (intakeResult) $("#intake-submit-btn").disabled = !intakeResult.can_submit;
    }
  });
}

