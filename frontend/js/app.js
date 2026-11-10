// Same origin when served by FastAPI. When index.html is opened straight from disk (file://)
// there is no server behind "/api", so fall back to the local dev server.
// Override with localStorage.setItem("koda-api", "https://…") if the API is hosted elsewhere.
const API = localStorage.getItem("koda-api") || (location.protocol === "file:" ? "http://localhost:8000" : "");
const OFFLINE_HINT = `Can't reach the backend at ${API || location.origin}. Start it with: cd backend && uvicorn app.main:app --reload, then open http://localhost:8000`;

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const money = (n, cur) => `${cur} ${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const label = (s) => s.replace(/_/g, " ");
const setStat = (key, val) => ($(`[data-stat="${key}"]`).textContent = val);

// Prevent browser Caret Browsing / text cursor on non-input elements.
const isEditable = (el) => el && el.closest?.("input, textarea, select, [contenteditable='true']");
addEventListener("mousedown", (e) => {
  if (!isEditable(e.target)) getSelection()?.removeAllRanges();
});
addEventListener("keydown", (e) => {
  if (!isEditable(document.activeElement) && ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
    getSelection()?.removeAllRanges();
  }
});

// Custom themed modal (confirm & notice)
let modalResolve = null;
function closeModal(result) {
  const modal = $("#confirm-modal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  if (modalResolve) {
    const r = modalResolve;
    modalResolve = null;
    r(result);
  }
}

function confirmModal({ eyebrow = "Confirm", title, message, confirmText = "Confirm", cancelText = "Cancel", danger = false, noticeOnly = false }) {
  const modal = $("#confirm-modal");
  if (!modal) return Promise.resolve(true);
  $("#modal-eyebrow").textContent = eyebrow;
  $("#modal-title").textContent = title;
  $("#modal-message").textContent = message;
  const cancelBtn = $("#modal-cancel");
  const confirmBtn = $("#modal-confirm");
  cancelBtn.hidden = noticeOnly;
  cancelBtn.textContent = cancelText;
  confirmBtn.textContent = confirmText;
  confirmBtn.className = `btn ${danger ? "btn-danger" : "btn-solid"}`;
  modal.hidden = false;
  confirmBtn.focus();
  return new Promise((resolve) => {
    modalResolve = resolve;
  });
}

function noticeModal(title, message, eyebrow = "Notice") {
  return confirmModal({ eyebrow, title, message, confirmText: "OK", noticeOnly: true });
}

$("#modal-cancel")?.addEventListener("click", () => closeModal(false));
$("#modal-confirm")?.addEventListener("click", () => closeModal(true));
$("#confirm-modal")?.addEventListener("click", (e) => {
  if (e.target.id === "confirm-modal") closeModal(false);
});
addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#confirm-modal")?.hidden) closeModal(false);
});

async function confirmAndDownload(url, labelText) {
  const ok = await confirmModal({
    eyebrow: "Confirm Download",
    title: `Download ${labelText}?`,
    message: "The file will be generated and downloaded to your device.",
    confirmText: "Download",
  });
  if (!ok) return;
  const a = document.createElement("a");
  a.href = url;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

// Theme
$("#theme-toggle")?.addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("koda-theme", next);
});

// Solid nav after scrolling past the hero
const nav = $(".nav");
if (nav) {
  addEventListener("scroll", () => nav.classList.toggle("scrolled", scrollY > $(".hero").offsetHeight * 0.8));
}

async function api(path, options = {}) {
  const headers = { ...options.headers };

  // Let the browser set multipart/form-data boundary.
  if (options.body instanceof FormData) {
    delete headers["Content-Type"];
  } else if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(API + path, {
    ...options,
    headers
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : res.statusText
    );
  }

  return res.status === 204 ? null : res.json();
}

/* ---------- Tabs ---------- */

const HERO = {
  documents: {
    eyebrow: "Koda · Overview",
    title: "Every document,<br />one list.",
    lede: "Invoices and orders side by side. Filter by any column; the CSV stays in step with every new order or invoice.",
  },
  invoices: {
    eyebrow: "Koda · Accounts Payable",
    title: "Every invoice,<br />checked against<br />every order.",
    lede: "Supplier invoices are read, matched to their purchase orders and flagged before anything reaches Dynamics.",
  },
  orders: {
    eyebrow: "Spectra · Order Automation",
    title: "Orders in.<br />Clean records out.",
    lede: "Purchase and sales orders are extracted from documents, validated line by line and exported for ERP entry.",
  },
  projects: {
    eyebrow: "EM Services · Project Tracker",
    title: "Every project,<br />every task,<br />one board.",
    lede: "Break estate and facilities work into tasks, assign owners and deadlines, and see what is slipping.",
  },
  planning: {
    eyebrow: "Koda · Production Planning",
    title: "Know what you<br />can build,<br />and what to buy.",
    lede: "Customer orders are broken into materials, checked against stock and deliveries, and ranked so planners can act on shortages early.",
  },
};
const loaded = {};

function showTab() {
  const tab = HERO[location.hash.slice(1)] ? location.hash.slice(1) : "documents";
  $$(".view").forEach((v) => (v.hidden = v.dataset.view !== tab));
  $$("[data-tab]").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  $("#hero-eyebrow").textContent = HERO[tab].eyebrow;
  $("#hero-title").innerHTML = HERO[tab].title;
  $("#hero-lede").textContent = HERO[tab].lede;
  if (!loaded[tab] || tab === "documents") {  // documents change from other tabs, so always refetch
    loaded[tab] = true;
    LOADERS[tab]().catch(() => {
      loaded[tab] = false;
      const container = $(`[data-view="${tab}"] tbody, [data-view="${tab}"] .cards`);
      if (container) {
        container.innerHTML = `<p class="muted">${esc(OFFLINE_HINT)}</p>`;
      }
    });
  }
}

addEventListener("hashchange", () => {
  showTab();
  const hero = $(".hero");
  if (hero && nav) {
    const contentTop = hero.offsetHeight - nav.offsetHeight;
    if (scrollY > contentTop) scrollTo({ top: contentTop });
  }
});

/* ---------- Documents overview ---------- */

const DOC_COLS = ["Document", "Type", "Company", "Date", "Amount", "Status"];
let documents = [];
const docFilters = {};

function renderDocuments() {
  DOC_COLS.forEach((col) => {
    const sel = $(`#documents-table select[data-col="${col}"]`);
    const values = [...new Set(documents.map((d) => d[col]).filter((v) => v !== ""))].sort();
    sel.innerHTML = `<option value="">All</option>` + values.map((v) => `<option value="${esc(v)}">${esc(label(v))}</option>`).join("");
    sel.value = values.includes(docFilters[col]) ? docFilters[col] : "";
    docFilters[col] = sel.value;
  });
  const shown = documents.filter((d) => DOC_COLS.every((c) => !docFilters[c] || d[c] === docFilters[c]));
  $("#document-rows").innerHTML = shown.length
    ? shown.map((d) => `<tr><td>${esc(d.Document)}</td><td>${esc(d.Type)}</td><td>${esc(d.Company)}</td><td>${esc(d.Date || "—")}</td>
        <td class="num">${d.Amount === "" ? "—" : money(d.Amount, d.Currency)}</td>
        <td><span class="pill ${esc(d.Status)}">${esc(label(d.Status))}</span></td></tr>`).join("")
    : `<tr><td colspan="6" class="muted">No documents match.</td></tr>`;
}

$("#documents-table")?.addEventListener("change", (e) => {
  if (!e.target.dataset.col) return;
  docFilters[e.target.dataset.col] = e.target.value;
  renderDocuments();
});

async function loadDocuments() {
  documents = await api("/api/documents");
  renderDocuments();
}

/* ---------- Koda: invoices ---------- */

function renderInvoiceDetail(inv) {
  if (!inv) return;
  const flags = inv.match?.flags?.length
    ? `<ul>${inv.match.flags.map((f) => `<li class="${f.level}">${esc(f.message)}</li>`).join("")}</ul>`
    : `<p class="muted" style="margin-top:1rem">All lines agree with ${esc(inv.po_number)}.</p>`;
  const lines = (inv.lines || [])
    .map((l) => `<tr><td>${esc(l.sku)}</td><td class="num">${l.qty}</td><td class="num">${Number(l.unit_price).toFixed(2)}</td></tr>`)
    .join("");
  $("#invoice-detail").innerHTML = `
    <span class="pill ${inv.match?.status || ""}">${inv.match?.status || ""}</span>
    <h3 style="margin-top:1rem">${esc(inv.invoice_number)}</h3>
    <p class="muted">${esc(inv.supplier)} · ${esc(inv.invoice_date)}</p>
    ${flags}
    <table><thead><tr><th>SKU</th><th class="num">Qty</th><th class="num">Unit</th></tr></thead><tbody>${lines}</tbody></table>
    <p style="margin-top:1rem" class="num"><strong>${money(inv.total, inv.currency)}</strong></p>
    ${
      inv.file_path
        ? `<button type="button" class="btn btn-outline" style="margin-top:1rem" id="open-invoice-pdf">Open PDF</button>`
        : ""
    }`;
  $("#open-invoice-pdf")?.addEventListener("click", () =>
    confirmAndDownload(`${API}/api/invoices/${encodeURIComponent(inv.invoice_number)}/file`, `${inv.invoice_number}.pdf`)
  );
}

function renderInvoices(invoices) {
  const count = (s) => invoices.filter((i) => i.match?.status === s).length;
  setStat("inv-total", invoices.length);
  setStat("inv-matched", count("matched"));
  setStat("inv-review", count("review"));
  setStat("inv-mismatch", count("mismatch"));

  const tbody = $("#invoice-rows");
  tbody.innerHTML = invoices
    .map(
      (inv, i) => `<tr data-i="${i}">
        <td>${esc(inv.invoice_number)}</td><td>${esc(inv.supplier)}</td><td>${esc(inv.po_number)}</td>
        <td class="num">${money(inv.total, inv.currency)}</td>
        <td><span class="pill ${inv.match?.status || ""}">${inv.match?.status || ""}</span></td>
        <td>${trashButton("invoice", inv.invoice_number)}</td></tr>`
    )
    .join("");
  selectableRows(tbody, (row) => renderInvoiceDetail(invoices[row.dataset.i]));
  $$("[data-trash=invoice]", tbody).forEach((btn) =>
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteRecord(`/api/invoices/${encodeURIComponent(btn.dataset.id)}`, `invoice ${btn.dataset.id}`);
    })
  );
}

const trashButton = (kind, id) =>
  `<button class="icon-btn trash" data-trash="${kind}" data-id="${esc(id)}" aria-label="Delete ${kind === "po" ? "purchase order" : kind} ${esc(id)}" title="Delete">
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>
  </button>`;

async function deleteRecord(path, name) {
  const ok = await confirmModal({
    eyebrow: "Confirm Delete",
    title: `Delete ${name}?`,
    message: "This record will be removed from the workspace until the server restarts and reloads sample data.",
    confirmText: "Delete",
    danger: true,
  });
  if (!ok) return;
  try {
    await api(path, { method: "DELETE" });
    await loadInvoices();
    $("#invoice-detail").innerHTML = `<p class="muted">No invoice selected.</p>`;
  } catch (err) {
    await noticeModal("Delete failed", err.message);
  }
}

function renderPurchaseOrders(orders, variants) {
  const options = Object.entries(variants)
    .map(([value, text]) => `<option value="${value}">${value} – ${esc(text)}</option>`)
    .join("");
  $("#po-cards").innerHTML = orders
    .map(
      (po) => `<div class="card po-card" data-po="${esc(po.po_number)}">
        <span class="accent">${esc(po.currency)}</span>
        <div class="card-top">${trashButton("po", po.po_number)}</div>
        <h4>${esc(po.po_number)}</h4>
        <p class="muted">${esc(po.supplier)}</p>
        <p class="muted">${po.lines.length} line(s)</p>
        <div class="po-invoice">
          <select aria-label="Invoice variant">${options}</select>
          <div class="actions">
            <button type="button" class="btn btn-outline btn-sm" data-action="download">Invoice PDF</button>
            <button type="button" class="btn btn-outline btn-sm" data-action="upload">Upload it</button>
          </div>
        </div></div>`
    )
    .join("");
  $$(".po-card").forEach((card) => {
    const pdfUrl = () => `${API}/api/purchase-orders/${encodeURIComponent(card.dataset.po)}/invoice.pdf?variant=${$("select", card).value}`;
    $("[data-trash=po]", card).addEventListener("click", () =>
      deleteRecord(`/api/purchase-orders/${encodeURIComponent(card.dataset.po)}`, `purchase order ${card.dataset.po}`)
    );
    $("[data-action=download]", card).addEventListener("click", () =>
      confirmAndDownload(pdfUrl(), `invoice PDF for ${card.dataset.po} (${$("select", card).value})`)
    );
    $("[data-action=upload]", card).addEventListener("click", (e) =>
      uploadGeneratedPdf(pdfUrl(), e.currentTarget, `invoice for ${card.dataset.po} (${$("select", card).value})`)
    );
  });
}

// Same path as a manual upload: fetch the generated PDF, then post it to the upload endpoint.
async function uploadGeneratedPdf(url, btn, description = "generated invoice PDF") {
  const ok = await confirmModal({
    eyebrow: "Confirm Upload",
    title: `Upload ${description}?`,
    message: "The invoice PDF will be generated, extracted by the server, and added to the review queue.",
    confirmText: "Upload",
  });
  if (!ok) return;
  btn.disabled = true;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
    const blob = await res.blob();
    const name = /filename="(.+)"/.exec(res.headers.get("Content-Disposition"))?.[1] || "invoice.pdf";
    const body = new FormData();
    body.append("file", new File([blob], name, { type: "application/pdf" }));
    const uploadRes = await fetch(API + "/api/invoices/upload", { method: "POST", body });
    const result = await uploadRes.json().catch(() => ({}));
    if (!uploadRes.ok) throw new Error(result.detail || result.error || uploadRes.statusText);
    await afterInvoiceUpload(result);
  } catch (err) {
    const out = $('[data-upload="/api/invoices/upload"]')?.nextElementSibling;
    if (out) {
      out.hidden = false;
      out.textContent = `Upload failed: ${err.message}\n${OFFLINE_HINT}`;
      out.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  } finally {
    btn.disabled = false;
  }
}

/* Create an invoice for one chosen product */

let products = [];
const productInvoiceUrl = () => {
  const qty = $("#pi-qty").value;
  return `${API}/api/products/${encodeURIComponent($("#pi-product").value)}/invoice.pdf?variant=${$("#pi-variant").value}${qty ? `&quantity=${qty}` : ""}`;
};

function renderProductInvoiceForm(list, variants) {
  products = list;
  $("#pi-product").innerHTML = list
    .map((p) => `<option value="${esc(p.sku)}">${esc(p.sku)} – ${esc(p.description)} (${esc(p.supplier)})</option>`)
    .join("");
  $("#pi-variant").innerHTML = Object.entries(variants)
    .map(([value, text]) => `<option value="${value}">${value} – ${esc(text)}</option>`)
    .join("");
  updateProductHint(true);
}

function updateProductHint(resetQty) {
  const p = products.find((x) => x.sku === $("#pi-product").value);
  if (!p) return;
  if (resetQty) $("#pi-qty").value = p.ordered_qty;
  $("#pi-hint").textContent = `${p.po_number} · ordered ${p.ordered_qty} at ${money(p.unit_price, p.currency)}. Billing more than ordered is flagged as a mismatch.`;
}

$("#pi-product")?.addEventListener("change", () => updateProductHint(true));
$("#pi-download")?.addEventListener("click", (e) => {
  e.preventDefault();
  const sku = $("#pi-product").value;
  const variant = $("#pi-variant").value;
  confirmAndDownload(productInvoiceUrl(), `invoice PDF for ${sku} (${variant})`);
});
$("#product-invoice")?.addEventListener("submit", (e) => {
  e.preventDefault();
  const sku = $("#pi-product").value;
  const variant = $("#pi-variant").value;
  uploadGeneratedPdf(productInvoiceUrl(), $("button[type=submit]", e.currentTarget), `invoice for ${sku} (${variant})`);
});

let invoices = [];

async function loadInvoices() {
  const [list, pos, variants, prods] = await Promise.all([
    api("/api/invoices"), api("/api/purchase-orders"), api("/api/invoice-variants"), api("/api/products"),
  ]);
  invoices = list;
  renderInvoices(invoices);
  renderPurchaseOrders(pos, variants);
  const chosen = { sku: $("#pi-product")?.value, qty: $("#pi-qty")?.value, variant: $("#pi-variant")?.value };
  renderProductInvoiceForm(prods, variants);
  if (products.some((p) => p.sku === chosen.sku)) {
    $("#pi-product").value = chosen.sku;
    $("#pi-qty").value = chosen.qty;
    $("#pi-variant").value = chosen.variant;
    updateProductHint(false);
  }
}

// Refresh the queue and open the uploaded invoice, or show the draft if fields were missing.
async function afterInvoiceUpload(result) {
  const out = $('[data-upload="/api/invoices/upload"]')?.nextElementSibling;
  if (out) out.hidden = false;

  if (!result.invoice) {
    if (out) {
      out.textContent = `Could not read every field (${result.draft?.note || "unrecognized format"}). Draft:\n` + JSON.stringify(result.draft, null, 2);
    }
    return;
  }

  if (out) {
    out.textContent = `${result.invoice.invoice_number} read from ${result.draft?.source_file || "document"} and added to the review queue (${result.invoice.match?.status || "pending"}).` +
      (result.saved
        ? " PDF and details saved to the database."
        : result.storage_error
          ? ` Not saved to the database: ${result.storage_error}`
          : "");
  }

  invoices = await api("/api/invoices");
  renderInvoices(invoices);

  const row = $(`#invoice-rows tr[data-i="${invoices.length - 1}"]`);
  if (row) {
    row.click();
    row.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function selectableRows(tbody, onSelect) {
  $$("tr", tbody).forEach((row) =>
    row.addEventListener("click", () => {
      $(".active", tbody)?.classList.remove("active");
      row.classList.add("active");
      onSelect(row);
    })
  );
}

/* ---------- Spectra: orders ---------- */

let orders = [];
let selectedOrderId = null;

const orderBadge = (o) => (o.status === "extracted" ? o.validation?.status : o.status);

function renderOrderDetail(o) {
  if (!o) return;
  const v = o.validation || { issues: [], flags: [], line_issues: [] };
  const issues = v.issues?.length
    ? `<ul>${v.issues.map((i) => `<li class="error">${esc(i)}</li>`).join("")}</ul>`
    : `<p class="muted" style="margin-top:1rem">All checks passed.</p>`;
  const warnings = (v.flags || []).filter((f) => f.level === "warning");
  const warningList = warnings.length ? `<ul>${warnings.map((f) => `<li class="warning">${esc(f.message)}</li>`).join("")}</ul>` : "";
  const lines = (o.lines || [])
    .map(
      (l, i) => `<tr${v.line_issues?.[i]?.length ? ' class="bad"' : ""}>
        <td>${esc(l.sku || "—")}<br /><span class="muted">${esc(l.description)}</span>
          ${(v.line_issues?.[i] || []).map((x) => `<br /><span class="line-issue">${esc(x)}</span>`).join("")}</td>
        <td class="num">${l.quantity}</td><td class="num">${Number(l.unit_price).toFixed(2)}</td><td class="num">${Number(l.amount).toFixed(2)}</td></tr>`
    )
    .join("");
  const canApprove = o.status === "extracted" && v.status === "ready";
  $("#order-detail").innerHTML = `
    <span class="pill ${orderBadge(o)}">${label(orderBadge(o) || "")}</span>
    <h3 style="margin-top:1rem">${esc(o.order_number || "No order number")}</h3>
    <p class="muted">${esc(o.counterparty)} · ${esc(o.type)} order</p>
    <p class="muted">Ordered ${esc(o.order_date || "—")} · Deliver ${esc(o.delivery_date || "—")} · from ${esc(o.source_file)}</p>
    ${issues}${warningList}
    <table><thead><tr><th>Item</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Amount</th></tr></thead><tbody>${lines}</tbody></table>
    <p style="margin-top:1rem" class="num"><strong>${money(o.total ?? v.line_total, o.currency)}</strong></p>
    <button class="btn btn-outline" style="margin-top:1rem" id="approve-order" ${canApprove ? "" : "disabled"}>
      ${o.status === "extracted" ? "Approve for export" : label(o.status)}</button>
    ${o.status === "extracted" ? `<button class="btn btn-outline" style="margin-top:1rem" id="edit-order">Edit</button>` : ""}`;
  $("#edit-order")?.addEventListener("click", () => renderOrderEditor(o));
  $("#approve-order")?.addEventListener("click", async () => {
    try {
      await api(`/api/orders/${o.id}/approve`, { method: "POST" });
      await loadOrders();
    } catch (err) {
      await noticeModal("Approval failed", err.message);
    }
  });
}

function renderOrderEditor(o) {
  const field = (name, text, type = "text") =>
    `<label class="edit-field">${text}<input name="${name}" type="${type}" value="${esc(o[name])}" /></label>`;
  const lineRow = (l = {}) => `<tr>
    <td><input name="sku" value="${esc(l.sku)}" /></td><td><input name="description" value="${esc(l.description)}" /></td>
    <td><input name="quantity" type="number" step="any" min="0" value="${esc(l.quantity)}" /></td>
    <td><input name="unit_price" type="number" step="any" min="0" value="${esc(l.unit_price)}" /></td>
    <td><button type="button" class="btn btn-outline btn-sm" data-drop-line>✕</button></td></tr>`;
  $("#order-detail").innerHTML = `
    <h3>Edit ${esc(o.id)}</h3>
    <p class="muted">Check the values against the original document (${esc(o.source_file)}).</p>
    <form id="order-edit">
      ${field("order_number", "Order number")}${field("counterparty", "Customer")}
      ${field("order_date", "Order date", "date")}${field("delivery_date", "Delivery date", "date")}${field("currency", "Currency")}
      <table class="edit-lines"><thead><tr><th>SKU</th><th>Description</th><th>Qty</th><th>Unit price</th><th></th></tr></thead>
        <tbody>${(o.lines || []).map(lineRow).join("")}</tbody></table>
      <button type="button" class="btn btn-outline btn-sm" id="add-line">+ Add line</button>
      <div style="margin-top:1rem"><button class="btn btn-outline" type="submit">Save and re-check</button>
        <button class="btn btn-outline" type="button" id="cancel-edit">Cancel</button></div>
    </form>`;
  const form = $("#order-edit");
  const tbody = $("tbody", form);
  form.addEventListener("click", (e) => e.target.matches("[data-drop-line]") && e.target.closest("tr").remove());
  $("#add-line").addEventListener("click", () => tbody.insertAdjacentHTML("beforeend", lineRow()));
  $("#cancel-edit").addEventListener("click", () => renderOrderDetail(o));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const val = (name) => form.elements[name].value;
    const body = {
      order_number: val("order_number"), counterparty: val("counterparty"), currency: val("currency"),
      order_date: val("order_date") || null, delivery_date: val("delivery_date") || null,
      lines: $$("tr", tbody).map((tr) => {
        const v = (n) => $(`[name=${n}]`, tr).value;
        return { sku: v("sku"), description: v("description"), quantity: Number(v("quantity")) || 0, unit_price: Number(v("unit_price")) || 0 };
      }),
    };
    try {
      await api(`/api/orders/${o.id}`, { method: "PATCH", body: JSON.stringify(body) });
      await loadOrders();
    } catch (err) {
      await noticeModal("Save failed", err.message);
    }
  });
}

async function afterOrderUpload(result) {
  const out = $('[data-upload="/api/orders/upload"]')?.nextElementSibling;
  selectedOrderId = result.order.id;
  await loadOrders();
  const v = result.order.validation || { status: "", issues: [] };
  if (out) {
    out.textContent = `${result.order.id} read from ${result.draft?.source_file || "document"} and added to the order queue (${label(v.status)}${v.issues?.length ? `: ${v.issues.join("; ")}` : ""}). Use Edit to correct it.`;
  }
  $("#order-detail")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderOrders() {
  const count = (fn) => orders.filter(fn).length;
  setStat("ord-total", orders.length);
  setStat("ord-ready", count((o) => o.status === "extracted" && o.validation?.status === "ready"));
  setStat("ord-attention", count((o) => o.status === "extracted" && o.validation?.status === "needs_attention"));
  setStat("ord-done", count((o) => o.status !== "extracted"));

  const tbody = $("#order-rows");
  tbody.innerHTML = orders
    .map(
      (o) => `<tr data-id="${o.id}" class="${o.id === selectedOrderId ? "active" : ""}">
        <td>${esc(o.order_number || "—")}</td><td>${esc(o.type)}</td><td>${esc(o.counterparty)}</td>
        <td class="num">${o.total == null ? "—" : money(o.total, o.currency)}</td>
        <td><span class="pill ${orderBadge(o)}">${label(orderBadge(o) || "")}</span></td>
        <td>${trashButton("order", o.order_number || o.id)}</td></tr>`
    )
    .join("");
  selectableRows(tbody, (row) => {
    selectedOrderId = row.dataset.id;
    renderOrderDetail(orders.find((o) => o.id === selectedOrderId));
  });
  $$("[data-trash=order]", tbody).forEach((btn) =>
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const id = btn.closest("tr").dataset.id;
      const ok = await confirmModal({
        eyebrow: "Confirm Delete",
        title: `Delete order ${btn.dataset.id}?`,
        message: "This order will be removed from the queue until the server restarts.",
        confirmText: "Delete",
        danger: true,
      });
      if (!ok) return;
      try {
        await api(`/api/orders/${id}`, { method: "DELETE" });
        if (selectedOrderId === id) {
          selectedOrderId = null;
          $("#order-detail").innerHTML = `<p class="muted">No order selected.</p>`;
        }
        await loadOrders();
      } catch (err) {
        await noticeModal("Delete failed", err.message);
      }
    })
  );
  const selected = orders.find((o) => o.id === selectedOrderId);
  if (selected) renderOrderDetail(selected);
}

async function loadOrders() {
  orders = await api("/api/orders");
  renderOrders();
}

$("#export-orders")?.addEventListener("click", async (e) => {
  e.preventDefault();
  await confirmAndDownload(e.currentTarget.href, "approved orders (orders.csv)");
  setTimeout(loadOrders, 800);
});

/* ---------- EM Services: projects ---------- */

let projects = [];
let project = null;
const STATUSES = { todo: "To do", in_progress: "In progress", done: "Done" };

function renderProjects() {
  const sum = (key) => projects.reduce((n, p) => n + (p[key] || 0), 0);
  setStat("prj-total", projects.length);
  setStat("prj-open", sum("task_count") - sum("done_count"));
  setStat("prj-overdue", sum("overdue_count"));
  setStat("prj-done", sum("done_count"));

  $("#project-cards").innerHTML = projects
    .map(
      (p) => `<button class="card project-card ${project?.id === p.id ? "selected" : ""}" data-id="${p.id}">
        <span class="pill ${p.health}">${label(p.health)}</span>
        <h4>${esc(p.name)}</h4>
        <p class="muted">${esc(p.site)} · ${esc(p.owner)} · due ${esc(p.due_date)}</p>
        <div class="progress"><span style="width:${(p.progress || 0) * 100}%"></span></div>
        <p class="muted">${p.done_count}/${p.task_count} tasks done${p.overdue_count ? ` · <span class="late">${p.overdue_count} overdue</span>` : ""}</p>
      </button>`
    )
    .join("");
  $$(".project-card").forEach((card) => card.addEventListener("click", () => openProject(card.dataset.id)));
}

function taskCard(t) {
  const options = Object.entries(STATUSES)
    .map(([value, text]) => `<option value="${value}" ${t.status === value ? "selected" : ""}>${text}</option>`)
    .join("");
  return `<div class="task ${t.overdue ? "overdue" : ""}" data-id="${t.id}">
    <p class="task-title">${esc(t.title)}</p>
    <p class="muted">${esc(t.owner || "Unassigned")} · ${t.due_date ? esc(t.due_date) : "no deadline"}${t.overdue ? ' · <span class="late">overdue</span>' : ""}</p>
    <div class="task-actions">
      <select aria-label="Status">${options}</select>
      <button class="link" aria-label="Delete task">Delete</button>
    </div>
  </div>`;
}

function renderBoard() {
  $("#board-title").textContent = project.name;
  $("#board-meta").textContent = project.brief;
  const owner = $("#owner-filter").value;
  const overdueOnly = $("#overdue-filter").checked;
  const visible = (project.tasks || []).filter((t) => (!owner || t.owner === owner) && (!overdueOnly || t.overdue));
  $$(".column").forEach((col) => {
    const tasks = visible.filter((t) => t.status === col.dataset.status);
    $("h3", col).textContent = `${STATUSES[col.dataset.status]} (${tasks.length})`;
    $(".tasks", col).innerHTML = tasks.map(taskCard).join("") || `<p class="muted empty">Nothing here.</p>`;
  });
  $$(".task").forEach((el) => {
    $("select", el).addEventListener("change", (e) => updateTask(el.dataset.id, { status: e.target.value }));
    $("button", el).addEventListener("click", () => deleteTask(el.dataset.id));
  });
}

async function openProject(id) {
  project = await api(`/api/projects/${id}`);
  $("#project-board").hidden = false;
  $("#ai-box").hidden = true;
  renderProjects();
  renderBoard();
}

async function refreshProjects() {
  projects = await api("/api/projects");
  if (project) project = await api(`/api/projects/${project.id}`);
  renderProjects();
  if (project) renderBoard();
}

async function updateTask(id, changes) {
  await api(`/api/tasks/${id}`, { method: "PATCH", body: JSON.stringify(changes) });
  await refreshProjects();
}

async function deleteTask(id) {
  const ok = await confirmModal({
    eyebrow: "Confirm Delete",
    title: "Delete this task?",
    message: "The task will be permanently removed from the project board.",
    confirmText: "Delete",
    danger: true,
  });
  if (!ok) return;
  await api(`/api/tasks/${id}`, { method: "DELETE" });
  await refreshProjects();
}

async function addTask(task) {
  await api(`/api/projects/${project.id}/tasks`, { method: "POST", body: JSON.stringify(task) });
  await refreshProjects();
}

$("#task-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target));
  await addTask({ title: data.title, owner: data.owner || null, due_date: data.due_date || null });
  e.target.reset();
});
$("#owner-filter")?.addEventListener("change", renderBoard);
$("#overdue-filter")?.addEventListener("change", renderBoard);

$("#btn-summary")?.addEventListener("click", async () => {
  const box = $("#ai-box");
  box.hidden = false;
  box.innerHTML = `<p class="muted">Summarizing…</p>`;
  const res = await api(`/api/projects/${project.id}/overdue-summary`);
  box.innerHTML = `<span class="accent">AI summary</span><p>${esc(res.summary)}</p>`;
});

$("#btn-suggest")?.addEventListener("click", async () => {
  const box = $("#ai-box");
  box.hidden = false;
  box.innerHTML = `<p class="muted">Reading the project brief…</p>`;
  const suggestions = await api(`/api/projects/${project.id}/suggest-tasks`, { method: "POST", body: "{}" });
  box.innerHTML = `<span class="accent">Suggested tasks</span>
    <div class="chips">${suggestions.map((s) => `<button class="chip">+ ${esc(s.title)}</button>`).join("")}</div>`;
  $$(".chip", box).forEach((chip, i) =>
    chip.addEventListener("click", async () => {
      chip.disabled = true;
      await addTask({ title: suggestions[i].title });
    })
  );
});

async function loadProjects() {
  const [list, members] = await Promise.all([api("/api/projects"), api("/api/members")]);
  projects = list;
  const options = members.map((m) => `<option>${esc(m)}</option>`).join("");
  $("#owner-filter")?.insertAdjacentHTML("beforeend", options);
  $("#task-form [name=owner]")?.insertAdjacentHTML("beforeend", options);
  renderProjects();
}

/* ---------- Koda: planning ---------- */

async function loadPlanning() {
  const p = await api("/api/planning");
  setStat("pln-orders", p.summary.orders);
  setStat("pln-ready", p.summary.ready);
  setStat("pln-inbound", p.summary.inbound);
  setStat("pln-short", p.summary.short);

  $("#plan-rows").innerHTML = p.sequence
    .map((s) => `<tr>
      <td>${s.rank}</td><td>${esc(s.order_number)}</td><td>${esc(s.customer)}</td><td>${esc(s.due_date)}</td>
      <td><span class="pill ${esc(s.priority)}">${esc(s.priority)}</span></td>
      <td><span class="pill ${esc(s.status)}">${esc(label(s.status))}</span></td>
      <td>${esc(s.action)}</td></tr>`)
    .join("");

  $("#material-rows").innerHTML = p.materials
    .map((m) => `<tr>
      <td>${esc(m.name)}<br /><span class="muted">${esc(m.sku)}</span></td>
      <td class="num">${m.required} ${esc(m.unit)}</td><td class="num">${m.on_hand}</td><td class="num">${m.inbound}</td>
      <td class="num">${m.shortfall || "–"}</td>
      <td><span class="pill ${esc(m.status)}">${esc(label(m.status))}</span></td></tr>`)
    .join("");

  $("#purchase-cards").innerHTML = p.purchase_suggestions.length
    ? p.purchase_suggestions
        .map((s) => `<div class="card"><h3>${esc(s.name)}</h3>
          <p>Buy at least <strong>${s.buy_qty}</strong> by ${esc(s.needed_by)}</p>
          <p class="muted">For ${s.for_orders.map(esc).join(", ")}</p></div>`)
        .join("")
    : `<p class="muted">No purchases needed.</p>`;
}

/* ---------- Uploads (invoices and orders) ---------- */

$$("form[data-upload]").forEach((form) => {
  const fileInput = $("input[type=file]", form);
  const out = form.nextElementSibling;
  const button = $('button[type="submit"]', form);
  const lbl = $("label", form);
  const defaultLabelHtml = lbl ? lbl.innerHTML : "<strong>Choose a file</strong> or drag it here";

  async function processSelectedFile(file) {
    if (!file) return;
    const allowedMimeTypes = ["application/pdf", "image/jpeg", "image/png", "image/webp"];
    const isPdfOrImage = allowedMimeTypes.includes(file.type) || /\.(pdf|jpe?g|png|webp)$/i.test(file.name);
    if (!isPdfOrImage) {
      out.hidden = false;
      out.textContent = "Only PDF, JPG, PNG and WEBP files are supported.";
      return;
    }

    const ok = await confirmModal({
      eyebrow: "Confirm Upload",
      title: `Upload ${file.name}?`,
      message: "This document will be sent to the server for field extraction and validation.",
      confirmText: "Upload",
    });
    if (!ok) return;

    const body = new FormData();
    body.append("file", file);

    out.hidden = false;
    out.textContent = "Uploading and extracting document...";

    if (button) {
      button.disabled = true;
      button.textContent = "Processing...";
    }

    try {
      const res = await fetch(API + form.dataset.upload, {
        method: "POST",
        body,
      });

      const result = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(result.detail || result.error || res.statusText);
      }

      if ("invoice" in result) {
        await afterInvoiceUpload(result);
      } else if (result.order) {
        await afterOrderUpload(result);
      } else {
        out.textContent =
          (result.draft?.note || "Document uploaded, but extraction was incomplete.") +
          "\n" +
          JSON.stringify(result.draft || result, null, 2);
      }

      fileInput.value = "";
      if (lbl) lbl.innerHTML = defaultLabelHtml;
    } catch (err) {
      out.textContent = `Upload failed: ${err.message}\n${OFFLINE_HINT}`;
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "Upload";
      }
    }
  }

  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (lbl) {
      lbl.innerHTML = file ? `<strong>${esc(file.name)}</strong>` : defaultLabelHtml;
    }
    if (file) processSelectedFile(file);
  });

  // Clicking anywhere on the empty part of the dashed box opens the file picker.
  form.addEventListener("click", (e) => {
    if (e.target === form) fileInput.click();
  });

  ["dragover", "dragleave", "drop"].forEach((evt) => {
    form.addEventListener(evt, (e) => {
      e.preventDefault();
      form.classList.toggle("drag", evt === "dragover");

      if (evt === "drop") {
        fileInput.files = e.dataTransfer.files;
        fileInput.dispatchEvent(new Event("change"));
      }
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = fileInput.files[0];
    if (!file) {
      fileInput.click();
      return;
    }
    await processSelectedFile(file);
  });
});

// Init
const LOADERS = { documents: loadDocuments, invoices: loadInvoices, orders: loadOrders, projects: loadProjects, planning: loadPlanning };
showTab();
