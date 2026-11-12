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
  if (e.key === "Escape") {
    if (!$("#confirm-modal")?.hidden) closeModal(false);
    const em = $("#po-email-modal");
    if (em && !em.hidden) em.hidden = true;
  }
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
  addEventListener("scroll", () => nav.classList.toggle("scrolled", scrollY > ($(".hero")?.offsetHeight || 200) * 0.7));
}

/* ---------- Sidebar & Nested Navigation ---------- */

const workspaceEl = $("#workspace");
const sidebarScrim = $("#sidebar-scrim");
const sidebarToggleBtn = $("#sidebar-toggle");
const isMobileLayout = () => innerWidth <= 960;

try {
  if (!isMobileLayout() && localStorage.getItem("koda-sb-collapsed") === "1") {
    workspaceEl?.classList.add("sidebar-collapsed");
    sidebarToggleBtn?.setAttribute("aria-expanded", "false");
  }
} catch {}

function closeMobileSidebar() {
  workspaceEl?.classList.remove("sidebar-open");
  if (sidebarScrim) sidebarScrim.hidden = true;
}

sidebarToggleBtn?.addEventListener("click", () => {
  if (!workspaceEl) return;
  if (isMobileLayout()) {
    const open = workspaceEl.classList.toggle("sidebar-open");
    if (sidebarScrim) sidebarScrim.hidden = !open;
    sidebarToggleBtn.setAttribute("aria-expanded", String(open));
  } else {
    const collapsed = workspaceEl.classList.toggle("sidebar-collapsed");
    sidebarToggleBtn.setAttribute("aria-expanded", String(!collapsed));
    try { localStorage.setItem("koda-sb-collapsed", collapsed ? "1" : "0"); } catch {}
  }
});
sidebarScrim?.addEventListener("click", closeMobileSidebar);

$$("[data-toggle-group]").forEach((btn) =>
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const grp = btn.closest(".sb-group");
    const open = grp.classList.toggle("open");
    btn.setAttribute("aria-expanded", String(open));
  })
);

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
const SECTION_ROUTES = {
  "orders/intake": { tab: "orders", section: "ord-intake" },
  "orders/queue": { tab: "orders", section: "ord-queue" },
  "orders/upload": { tab: "orders", section: "ord-upload" },
  "documents/all": { tab: "documents", section: "doc-all" },
  "invoices/queue": { tab: "invoices", section: "inv-queue" },
  "invoices/pos": { tab: "invoices", section: "inv-pos" },
  "invoices/create": { tab: "invoices", section: "inv-create" },
  "invoices/upload": { tab: "invoices", section: "inv-upload" },
  "projects/list": { tab: "projects", section: "prj-list" },
  "projects/board": { tab: "projects", section: "project-board" },
  "planning/build": { tab: "planning", section: "pln-build" },
  "planning/materials": { tab: "planning", section: "pln-materials" },
  "planning/purchases": { tab: "planning", section: "pln-purchases" },
};
const DEFAULT_SECTION = {
  orders: "ord-intake",
  documents: "doc-all",
  invoices: "inv-queue",
  projects: "prj-list",
  planning: "pln-build",
};
const loaded = {};

function parseRoute() {
  const raw = location.hash.slice(1);
  if (SECTION_ROUTES[raw]) return SECTION_ROUTES[raw];
  const tab = HERO[raw] ? raw : "documents";
  return { tab, section: DEFAULT_SECTION[tab] || null };
}

function updateSidebarActive(tab, section) {
  $$(".sb-group").forEach((grp) => {
    const isTab = grp.dataset.group === tab;
    $(".sb-parent-row", grp)?.classList.toggle("active", isTab);
    if (isTab) {
      grp.classList.add("open");
      $(".sb-chev", grp)?.setAttribute("aria-expanded", "true");
    }
  });
  $$(".sb-child").forEach((a) => a.classList.toggle("active", a.dataset.section === section));
  $$(".block.section-focus").forEach((b) => b.classList.remove("section-focus"));
  if (section) $(`#${section}`)?.classList.add("section-focus");
}

function focusSection(section) {
  if (!section) return;
  const el = $(`#${section}`);
  if (!el) return;
  if (section === "project-board" && el.hidden) {
    $("#prj-list")?.scrollIntoView({ behavior: "smooth", block: "start" });
    return;
  }
  requestAnimationFrame(() => el.scrollIntoView({ behavior: "smooth", block: "start" }));
}

function showTab(scrollToSection = false) {
  const { tab, section } = parseRoute();
  $$(".view").forEach((v) => (v.hidden = v.dataset.view !== tab));
  $$("[data-tab]").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  updateSidebarActive(tab, section);
  $("#hero-eyebrow").textContent = HERO[tab].eyebrow;
  $("#hero-title").innerHTML = HERO[tab].title;
  $("#hero-lede").textContent = HERO[tab].lede;
  const done = () => {
    if (scrollToSection && location.hash.includes("/")) focusSection(section);
  };
  if (!loaded[tab] || tab === "documents") {  // documents change from other tabs, so always refetch
    loaded[tab] = true;
    LOADERS[tab]()
      .then(done)
      .catch(() => {
        loaded[tab] = false;
        const container = $(`[data-view="${tab}"] tbody, [data-view="${tab}"] .cards`);
        if (container) {
          container.innerHTML = `<p class="muted">${esc(OFFLINE_HINT)}</p>`;
        }
      });
  } else {
    done();
  }
  closeMobileSidebar();
}

addEventListener("hashchange", () => {
  showTab(true);
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
    .map((l) => {
      const item = l.sku ? esc(l.sku) : `<span class="muted">${esc(l.description || "—")} (no SKU)</span>`;
      return `<tr><td>${item}</td><td class="num">${l.qty}</td><td class="num">${Number(l.unit_price).toFixed(2)}</td></tr>`;
    })
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
  const rank = (e) => (e.invoice.status === "pending" ? 0 : 1); // awaiting invoice first
  const approved = [...invoiceQueue].sort((a, b) => rank(a) - rank(b))
    .map((e) => `<tr data-iq="${esc(e.order_id)}" class="${e.order_id === selectedInvoiceId ? "active" : ""}">
        <td>${esc(e.invoice.invoice_number)}<br /><span class="muted">${esc(e.transaction_id)}</span></td>
        <td>${esc(e.invoice.customer.name)}</td><td>${esc(e.order_number || e.order_id)}</td>
        <td class="num">${money(e.invoice.total, e.invoice.currency)}</td>
        <td><span class="pill ${e.invoice.status}">${e.invoice.status === "pending" ? "awaiting invoice" : "generated"}</span></td>
        <td></td></tr>`)
    .join("");
  tbody.innerHTML = approved + invoices
    .map(
      (inv, i) => `<tr data-i="${i}">
        <td>${esc(inv.invoice_number)}</td><td>${esc(inv.supplier)}</td><td>${esc(inv.po_number)}</td>
        <td class="num">${money(inv.total, inv.currency)}</td>
        <td><span class="pill ${inv.match?.status || ""}">${inv.match?.status || ""}</span></td>
        <td>${trashButton("invoice", inv.invoice_number)}</td></tr>`
    )
    .join("");
  selectableRows(tbody, (row) => {
    if (row.dataset.iq) {
      selectedInvoiceId = row.dataset.iq;
      renderInvoiceEditor(invoiceQueue.find((e) => e.order_id === selectedInvoiceId));
    } else {
      selectedInvoiceId = null;
      renderInvoiceDetail(invoices[row.dataset.i]);
    }
  });
  const selected = invoiceQueue.find((e) => e.order_id === selectedInvoiceId);
  if (selected) renderInvoiceEditor(selected);
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
        <p class="muted">${po.lines.length} line(s)${po.auto_created ? ` · auto-created from ${esc(po.source_invoice)}` : ""}</p>
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
  const [list, pos, variants, prods, queue] = await Promise.all([
    api("/api/invoices"), api("/api/purchase-orders"), api("/api/invoice-variants"), api("/api/products"), api("/api/invoice-queue"),
  ]);
  invoices = list;
  invoiceQueue = queue;
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
    const filled = (result.invoice.auto_filled || []).map(label);
    out.textContent = `${result.invoice.invoice_number} read from ${result.draft?.source_file || "document"} and added to the review queue (${result.invoice.match?.status || "pending"}).` +
      (filled.length ? ` Auto-filled: ${filled.join(", ")}.` : "") +
      (result.saved
        ? " PDF and details saved to the database."
        : result.storage_error
          ? ` Not saved to the database: ${result.storage_error}`
          : "");
  }

  await loadInvoices(); // also refreshes the PO cards, which may now include an auto-created PO

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
let invoiceQueue = []; // approved transactions awaiting / with a generated invoice
let selectedInvoiceId = null;
let catalog = [];
let selectedOrderId = null;

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—");

const adminInput = $("#admin-name");
if (adminInput) {
  try { adminInput.value = localStorage.getItem("koda-admin") || ""; } catch {}
  adminInput.addEventListener("change", () => {
    try { localStorage.setItem("koda-admin", adminInput.value.trim()); } catch {}
  });
}

// Every approval, rejection and invoice edit is recorded against the administrator's name.
async function adminName() {
  if (!adminInput) return "Administrator"; // no name field on the page: record a generic administrator
  const name = adminInput.value.trim();
  if (name) return name;
  await noticeModal("Who is approving?", "Enter your name in the Administrator field above the order queue first.", "Administrator required");
  adminInput?.focus();
  return null;
}

function approvalRecord(o) {
  const a = o.approval;
  if (!a) return "";
  return `<div class="audit ${a.decision}">
    <strong>${a.decision === "approved" ? "Approved" : "Rejected"}</strong> by ${esc(a.by)} on ${esc(fmtTime(a.at))}
    ${a.reason ? `<br /><span class="muted">Reason: ${esc(a.reason)}</span>` : ""}
    ${a.decision === "rejected" ? `<br /><span class="muted">Rejected transactions are not invoiced or exported.</span>` : ""}
  </div>`;
}

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
    <p class="muted">${esc(o.counterparty)} · ${esc(o.type)} order · ${esc(o.transaction_id)}</p>
    <p class="muted">Ordered ${esc(o.order_date || "—")} · Deliver ${esc(o.delivery_date || "—")} · from ${esc(o.source_file)}</p>
    ${issues}${warningList}
    <table><thead><tr><th>Item</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Amount</th></tr></thead><tbody>${lines}</tbody></table>
    <p style="margin-top:1rem" class="num"><strong>${money(o.total ?? v.line_total, o.currency)}</strong></p>
    ${approvalRecord(o)}
    ${o.status === "extracted" ? `<div class="actions">
      <button class="btn btn-solid" id="approve-order" ${canApprove ? "" : 'disabled title="Fix validation issues first"'}>Approve transaction</button>
      <button class="btn btn-danger" id="reject-order">Reject transaction</button>
      <button class="btn btn-outline" id="edit-order">Edit order</button></div>
      <div class="reject-box" id="reject-box" hidden>
        <label class="edit-field">Reason for rejection<textarea id="reject-reason" rows="2" maxlength="500"></textarea></label>
        <div class="actions"><button class="btn btn-danger btn-sm" id="reject-confirm">Confirm rejection</button>
          <button class="btn btn-outline btn-sm" id="reject-cancel">Cancel</button></div>
      </div>` : orderLocked(o) ? `<p class="muted" style="margin-top:1rem">${esc(orderLocked(o))}</p>`
      : `<div class="actions"><button class="btn btn-outline" id="edit-order">Edit order / status</button></div>`}
    ${o.updated_at ? `<p class="muted" style="margin-top:.6rem;font-size:.8rem">Last edited by ${esc(o.updated_by)} · ${esc(fmtTime(o.updated_at))}</p>` : ""}`;
  $("#edit-order")?.addEventListener("click", () => renderOrderForm(o));
  $("#approve-order")?.addEventListener("click", async () => {
    const by = await adminName();
    if (!by) return;
    const ok = await confirmModal({
      eyebrow: "Approve Transaction",
      title: `Approve ${o.order_number || o.id}?`,
      message: `${o.transaction_id} will be marked Approved by ${by} and moved to the Review queue on the Invoices tab.`,
      confirmText: "Approve",
    });
    if (!ok) return;
    try {
      await api(`/api/orders/${o.id}/approve`, { method: "POST", body: JSON.stringify({ approved_by: by }) });
      selectedInvoiceId = o.id;
      await loadOrders();
    } catch (err) {
      await noticeModal("Approval failed", err.message);
    }
  });
  $("#reject-order")?.addEventListener("click", () => {
    $("#reject-box").hidden = false;
    $("#reject-reason").focus();
  });
  $("#reject-cancel")?.addEventListener("click", () => ($("#reject-box").hidden = true));
  $("#reject-confirm")?.addEventListener("click", async () => {
    const by = await adminName();
    if (!by) return;
    const ok = await confirmModal({
      eyebrow: "Reject Transaction",
      title: `Reject ${o.order_number || o.id}?`,
      message: "A rejected transaction is kept on file but never invoiced or exported.",
      confirmText: "Reject",
      danger: true,
    });
    if (!ok) return;
    try {
      await api(`/api/orders/${o.id}/reject`, {
        method: "POST",
        body: JSON.stringify({ rejected_by: by, reason: $("#reject-reason").value }),
      });
      await loadOrders();
    } catch (err) {
      await noticeModal("Rejection failed", err.message);
    }
  });
}

// Why an order can no longer be edited, or "" if it can.
function orderLocked(o) {
  if (o.status === "exported") return "Exported to the ERP, so this order can no longer be edited.";
  if (o.invoice?.status === "generated") return "Its invoice has been generated, so this order can no longer be edited.";
  return "";
}

const STATUS_LABEL = { extracted: "Pending", approved: "Approved", rejected: "Rejected" };

const orderItemRow = (l = { description: "", sku: "", quantity: 1, unit_price: 0 }) => `<div class="iq-item">
  <div class="iq-item-head">
    <input name="description" value="${esc(l.description)}" list="catalog-names" placeholder="Item" aria-label="Item" maxlength="200" />
    <button type="button" class="icon-btn" data-remove aria-label="Remove item" title="Remove item">✕</button>
  </div>
  <input name="sku" value="${esc(l.sku)}" placeholder="SKU (filled in for catalogue items)" aria-label="SKU" maxlength="40" />
  <div class="iq-item-row">
    <div class="qty"><button type="button" class="btn btn-outline btn-sm" data-step="-1" aria-label="Decrease quantity">−</button>
      <input name="quantity" type="number" min="0.01" step="any" value="${esc(l.quantity)}" aria-label="Qty" required />
      <button type="button" class="btn btn-outline btn-sm" data-step="1" aria-label="Increase quantity">+</button></div>
    <label class="price">× <input name="unit_price" type="number" min="0" step="0.01" value="${esc(l.unit_price)}" aria-label="Unit price" required /></label>
    <span class="amount" data-amount></span>
  </div></div>`;

// One form for both "+ Add New Order" (o = null) and editing an existing order in place.
function renderOrderForm(o = null) {
  const isNew = !o;
  const d = o || { order_number: "", type: "sales", counterparty: "", order_date: new Date().toISOString().slice(0, 10), delivery_date: "", currency: "SGD", lines: [{}], status: "extracted" };
  const field = (name, text, type = "text", extra = "") =>
    `<label class="edit-field">${text}<input name="${name}" type="${type}" value="${esc(d[name])}" ${extra} /></label>`;
  $("#order-detail").innerHTML = `
    <h3>${isNew ? "New order" : `Edit ${esc(o.order_number || o.id)}`}</h3>
    <p class="muted">${isNew ? "Key in an order by hand. It joins the queue as Pending." : `Changes are saved to this record (${esc(o.transaction_id)}), not as a new order.`}</p>
    <form id="order-form" novalidate>
      ${field("order_number", "Order number", "text", 'required maxlength="40"')}
      <label class="edit-field">Type<select name="type">
        <option value="sales" ${d.type === "sales" ? "selected" : ""}>Sales order</option>
        <option value="purchase" ${d.type === "purchase" ? "selected" : ""}>Purchase order</option></select></label>
      ${field("counterparty", "Customer / supplier", "text", 'required maxlength="120"')}
      <div style="display:flex;gap:1rem">
        <div style="flex:1">${field("order_date", "Order date", "date", "required")}</div>
        <div style="flex:1">${field("delivery_date", "Delivery date", "date")}</div>
      </div>
      ${field("currency", "Currency", "text", 'required minlength="3" maxlength="3" style="text-transform:uppercase"')}
      ${isNew ? "" : `<label class="edit-field">Status<select name="status">
        ${Object.entries(STATUS_LABEL).map(([k, v]) => `<option value="${k}" ${o.status === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
        <label class="edit-field" id="status-reason" hidden>Reason for rejection<textarea name="reason" rows="2" maxlength="500"></textarea></label>
        ${o.status !== "extracted" ? `<p class="muted" style="font-size:.8rem;margin-top:.4rem">Saving reopens this ${STATUS_LABEL[o.status].toLowerCase()} order, then applies the status you pick. Approving again re-checks it and makes a new invoice draft.</p>` : ""}`}
      <h4 style="margin-top:1rem">Items</h4>
      <div class="iq-items" id="order-items">${(d.lines.length ? d.lines : [{}]).map((l) => orderItemRow({ description: "", sku: "", quantity: 1, unit_price: 0, ...l })).join("")}</div>
      <button type="button" class="btn btn-outline btn-sm" id="order-add-item">+ Add item</button>
      <div class="iq-totals"><span class="grand">Order total</span><span class="num grand" id="order-total"></span></div>
      <div class="actions">
        <button class="btn btn-solid" type="submit">${isNew ? "Create order" : "Save changes"}</button>
        <button class="btn btn-outline" type="button" id="cancel-edit">Cancel</button>
      </div>
    </form>`;

  const form = $("#order-form");
  const list = $("#order-items", form);
  const byName = Object.fromEntries(catalog.map((c) => [c.name.toLowerCase(), c]));
  const collect = () => ({
    order_number: form.elements.order_number.value.trim(),
    type: form.elements.type.value,
    counterparty: form.elements.counterparty.value.trim(),
    order_date: form.elements.order_date.value || null,
    delivery_date: form.elements.delivery_date.value || null,
    currency: form.elements.currency.value.trim().toUpperCase(),
    lines: $$(".iq-item", list).map((card) => {
      const v = (n) => $(`[name=${n}]`, card).value;
      return { description: v("description").trim(), sku: v("sku").trim() || null, quantity: Number(v("quantity")) || 0, unit_price: Number(v("unit_price")) || 0 };
    }),
  });
  const recalc = () => {
    const data = collect();
    let total = 0;
    $$(".iq-item", list).forEach((card, n) => {
      const amount = round2(data.lines[n].quantity * data.lines[n].unit_price);
      total += amount;
      $("[data-amount]", card).textContent = money(amount, data.currency || "SGD");
    });
    $("#order-total").textContent = money(round2(total), data.currency || "SGD");
  };
  const statusSel = form.elements.status;
  statusSel?.addEventListener("change", () => ($("#status-reason").hidden = statusSel.value !== "rejected"));

  form.addEventListener("input", (ev) => {
    // Picking a catalogue item fills its SKU and list price.
    if (ev.target.name === "description") {
      const item = byName[ev.target.value.trim().toLowerCase()];
      const card = ev.target.closest(".iq-item");
      if (item) {
        $("[name=sku]", card).value = item.sku;
        const price = $("[name=unit_price]", card);
        if (!Number(price.value)) price.value = item.unit_price;
      }
    }
    recalc();
  });
  form.addEventListener("click", (ev) => {
    const step = ev.target.closest("[data-step]");
    if (step) {
      const input = $("[name=quantity]", step.closest(".iq-item"));
      input.value = Math.max(1, (Number(input.value) || 0) + Number(step.dataset.step));
      recalc();
    }
    if (ev.target.closest("[data-remove]")) {
      if ($$(".iq-item", list).length === 1) return noticeModal("At least one item", "An order needs at least one item.");
      ev.target.closest(".iq-item").remove();
      recalc();
    }
  });
  $("#order-add-item").addEventListener("click", () => {
    list.insertAdjacentHTML("beforeend", orderItemRow());
    $(".iq-item:last-child [name=description]", list).focus();
    recalc();
  });
  $("#cancel-edit").addEventListener("click", () => (o ? renderOrderDetail(o) : ($("#order-detail").innerHTML = `<p class="muted">No order selected.</p>`)));

  // Empty item rows (no name, no price) are dropped rather than blocking the save; anything else
  // missing is listed in a dialog, since the browser's own validation bubble is easy to miss here.
  const isBlank = (card) => !$("[name=description]", card).value.trim() && !$("[name=sku]", card).value.trim() && !Number($("[name=unit_price]", card).value);
  const problems = () => {
    $$(".invalid", form).forEach((el) => el.classList.remove("invalid"));
    const out = [];
    const need = (el, msg) => {
      if (!el.checkValidity() || !el.value.trim()) {
        el.classList.add("invalid");
        out.push(msg);
      }
    };
    need(form.elements.order_number, "Order number is required.");
    need(form.elements.counterparty, "Customer / supplier is required.");
    need(form.elements.order_date, "Order date is required.");
    if (!/^[A-Za-z]{3}$/.test(form.elements.currency.value.trim())) {
      form.elements.currency.classList.add("invalid");
      out.push("Currency must be a 3-letter code, e.g. SGD.");
    }
    const cards = $$(".iq-item", list).filter((c) => !isBlank(c));
    if (!cards.length) out.push("Add at least one item.");
    cards.forEach((card) => {
      const n = $$(".iq-item", list).indexOf(card) + 1;
      need($("[name=description]", card), `Item ${n} needs a name.`);
      const qty = $("[name=quantity]", card);
      if (!(Number(qty.value) > 0)) { qty.classList.add("invalid"); out.push(`Item ${n}: quantity must be more than 0.`); }
      const price = $("[name=unit_price]", card);
      if (price.value === "" || Number(price.value) < 0) { price.classList.add("invalid"); out.push(`Item ${n}: unit price can't be negative.`); }
    });
    return out;
  };

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const issues = problems();
    if (issues.length) {
      $(".invalid", form)?.focus();
      return noticeModal("Check the order", issues.join(" "), "Can't save yet");
    }
    const by = await adminName();
    if (!by) return;
    $$(".iq-item", list).filter(isBlank).forEach((card) => card.remove());
    recalc();
    const body = collect();
    try {
      if (isNew) {
        const created = await api("/api/orders", { method: "POST", body: JSON.stringify({ ...body, created_by: by }) });
        selectedOrderId = created.id;
      } else {
        const want = statusSel.value;
        const reason = form.elements.reason?.value || "";
        if (o.status === "extracted") {
          await api(`/api/orders/${o.id}`, { method: "PATCH", body: JSON.stringify({ ...body, updated_by: by, ...(want !== "extracted" ? { status: want, reason } : {}) }) });
        } else {
          // Reopen and save the edits, then apply the chosen status.
          await api(`/api/orders/${o.id}`, { method: "PATCH", body: JSON.stringify({ ...body, status: "extracted", updated_by: by }) });
          if (want !== "extracted") {
            try {
              await api(`/api/orders/${o.id}`, { method: "PATCH", body: JSON.stringify({ status: want, updated_by: by, reason }) });
            } catch (err) {
              await loadOrders();
              return noticeModal("Saved as Pending", `Your changes were saved, but the order could not be set to ${STATUS_LABEL[want]}: ${err.message}`);
            }
          }
        }
      }
      await loadOrders();
    } catch (err) {
      await noticeModal(isNew ? "Could not create order" : "Save failed", err.message);
    }
  });
  recalc();
  form.elements.order_number.focus();
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

async function loadOrders() {
  [orders, invoiceQueue, catalog] = await Promise.all([api("/api/orders"), api("/api/invoice-queue"), api("/api/catalog")]);
  $("#catalog-names").innerHTML = catalog.map((c) => `<option value="${esc(c.name)}">${esc(c.sku)} · ${c.unit_price.toFixed(2)}</option>`).join("");
  wireIntakeEvents();
  await loadIntakeSamples().catch(() => {});
  renderOrders();
  renderInvoiceQueue();
}

/* ---------- Spectra: review invoice queue ---------- */

const round2 = (n) => Math.round((n + Number.EPSILON) * 100) / 100;

// Approved transactions are shown in the Invoices tab's review queue.
function renderInvoiceQueue() {
  if ($("#invoice-rows")) renderInvoices(invoices);
}

function invoiceRefs(e) {
  const a = e.approval || {};
  const inv = e.invoice;
  return `<dl class="ref-grid">
    <dt>Order ID</dt><dd>${esc(e.order_number || e.order_id)}</dd>
    <dt>Transaction ID</dt><dd>${esc(e.transaction_id)}</dd>
    <dt>Approved</dt><dd>${esc(a.by || "—")} · ${esc(fmtTime(a.at))}</dd>
    ${inv.updated_at ? `<dt>Last edited</dt><dd>${esc(inv.updated_by)} · ${esc(fmtTime(inv.updated_at))}</dd>` : ""}
    ${inv.generated_at ? `<dt>Generated</dt><dd>${esc(inv.generated_by)} · ${esc(fmtTime(inv.generated_at))}</dd>` : ""}
  </dl>`;
}

function totalsHtml(t, currency, taxRate) {
  return `<div class="iq-totals">
    <span>Subtotal</span><span class="num">${money(t.subtotal, currency)}</span>
    <span>Tax (${round2(taxRate * 100)}%)</span><span class="num">${money(t.tax, currency)}</span>
    <span class="grand">Total</span><span class="num grand">${money(t.total, currency)}</span></div>`;
}

function renderGeneratedInvoice(e) {
  const inv = e.invoice;
  const c = inv.customer;
  $("#invoice-detail").innerHTML = `<span class="pill generated">generated</span>
    <h3 style="margin-top:1rem">${esc(inv.invoice_number)}</h3>
    <p class="muted">${[c.name, c.address, c.email].filter(Boolean).map(esc).join(" · ")}</p>
    ${invoiceRefs(e)}
    <table><thead><tr><th>Item</th><th class="num">Qty</th><th class="num">Unit</th><th class="num">Amount</th></tr></thead><tbody>
    ${inv.items.map((i) => `<tr><td>${esc(i.name)}${i.description ? `<br /><span class="muted">${esc(i.description)}</span>` : ""}</td>
      <td class="num">${i.quantity}</td><td class="num">${Number(i.unit_price).toFixed(2)}</td><td class="num">${Number(i.amount).toFixed(2)}</td></tr>`).join("")}
    </tbody></table>
    ${totalsHtml(inv, inv.currency, inv.tax_rate)}
    <div class="actions"><a class="btn btn-outline" id="iq-download" href="${API}/api/invoice-queue/${e.order_id}/invoice.pdf">Download PDF</a></div>`;
  $("#iq-download").addEventListener("click", (ev) => {
    ev.preventDefault();
    confirmAndDownload(ev.currentTarget.href, `invoice ${inv.invoice_number}`);
  });
}

const invoiceItemRow = (i = { name: "", description: "", quantity: 1, unit_price: 0 }) => `<div class="iq-item">
  <div class="iq-item-head">
    <input name="name" value="${esc(i.name)}" placeholder="Item name" aria-label="Item name" required maxlength="120" />
    <button type="button" class="icon-btn" data-remove aria-label="Remove item" title="Remove item">✕</button>
  </div>
  <input name="description" value="${esc(i.description)}" placeholder="Description (optional)" aria-label="Description" maxlength="300" />
  <div class="iq-item-row">
    <div class="qty"><button type="button" class="btn btn-outline btn-sm" data-step="-1" aria-label="Decrease quantity">−</button>
      <input name="quantity" type="number" min="0.01" step="any" value="${esc(i.quantity)}" aria-label="Quantity" required />
      <button type="button" class="btn btn-outline btn-sm" data-step="1" aria-label="Increase quantity">+</button></div>
    <label class="price">× <input name="unit_price" type="number" min="0" step="0.01" value="${esc(i.unit_price)}" aria-label="Unit price" required /></label>
    <span class="amount" data-amount></span>
  </div></div>`;

function renderInvoiceEditor(e) {
  if (!e) return;
  if (e.invoice.status !== "pending") return renderGeneratedInvoice(e);
  const inv = e.invoice;
  $("#invoice-detail").innerHTML = `<span class="pill pending">awaiting invoice</span>
    <form id="iq-form" novalidate>
      <label class="edit-field">Invoice number<input name="invoice_number" value="${esc(inv.invoice_number)}" required maxlength="40" /></label>
      ${invoiceRefs(e)}
      <h4 style="margin-top:1rem">Customer</h4>
      <label class="edit-field">Name<input name="c_name" value="${esc(inv.customer.name)}" required maxlength="120" /></label>
      <label class="edit-field">Address<textarea name="c_address" rows="2" maxlength="300">${esc(inv.customer.address)}</textarea></label>
      <label class="edit-field">Email<input name="c_email" type="email" value="${esc(inv.customer.email)}" maxlength="120" /></label>
      <div style="display:flex;gap:1rem">
        <label class="edit-field" style="flex:1">Issue date<input name="issue_date" type="date" value="${esc(inv.issue_date)}" required /></label>
        <label class="edit-field" style="flex:1">Tax rate (%)<input name="tax_pct" type="number" min="0" max="100" step="0.01" value="${round2(inv.tax_rate * 100)}" required /></label>
      </div>
      <h4 style="margin-top:1rem">Items</h4>
      <div class="iq-items" id="iq-items">${inv.items.map(invoiceItemRow).join("")}</div>
      <button type="button" class="btn btn-outline btn-sm" id="iq-add">+ Add item</button>
      <div id="iq-totals-slot"></div>
      <div class="actions">
        <button type="submit" class="btn btn-solid" id="iq-generate">Generate invoice</button>
        <button type="button" class="btn btn-outline" id="iq-save">Save draft</button>
        <button type="button" class="btn btn-outline" id="iq-reset">Discard changes</button>
      </div>
    </form>`;

  const form = $("#iq-form");
  const list = $("#iq-items", form);
  const collect = () => ({
    invoice_number: form.elements.invoice_number.value.trim(),
    customer: { name: form.elements.c_name.value, address: form.elements.c_address.value, email: form.elements.c_email.value },
    issue_date: form.elements.issue_date.value,
    tax_rate: (Number(form.elements.tax_pct.value) || 0) / 100,
    items: $$(".iq-item", list).map((card) => {
      const v = (n) => $(`[name=${n}]`, card).value;
      return { name: v("name").trim(), description: v("description"), quantity: Number(v("quantity")) || 0, unit_price: Number(v("unit_price")) || 0 };
    }),
  });
  // Live preview using the server's rounding; the server recomputes totals on save.
  const recalc = () => {
    const d = collect();
    let subtotal = 0;
    $$(".iq-item", list).forEach((card, n) => {
      const amount = round2(d.items[n].quantity * d.items[n].unit_price);
      subtotal += amount;
      $("[data-amount]", card).textContent = money(amount, inv.currency);
    });
    subtotal = round2(subtotal);
    const tax = round2(subtotal * d.tax_rate);
    $("#iq-totals-slot").innerHTML = totalsHtml({ subtotal, tax, total: round2(subtotal + tax) }, inv.currency, d.tax_rate);
  };
  const save = async (by) => {
    if (!form.reportValidity()) return null;
    const d = collect();
    if (!d.items.length) {
      await noticeModal("No items", "An invoice needs at least one item.");
      return null;
    }
    try {
      return await api(`/api/invoice-queue/${e.order_id}`, { method: "PUT", body: JSON.stringify({ ...d, edited_by: by }) });
    } catch (err) {
      await noticeModal("Save failed", err.message);
      return null;
    }
  };

  form.addEventListener("input", recalc);
  form.addEventListener("click", (ev) => {
    const step = ev.target.closest("[data-step]");
    if (step) {
      const input = $("[name=quantity]", step.closest(".iq-item"));
      input.value = Math.max(1, (Number(input.value) || 0) + Number(step.dataset.step));
      recalc();
    }
    if (ev.target.closest("[data-remove]")) {
      ev.target.closest(".iq-item").remove();
      recalc();
    }
  });
  $("#iq-add").addEventListener("click", () => {
    list.insertAdjacentHTML("beforeend", invoiceItemRow());
    $(".iq-item:last-child [name=name]", list).focus();
    recalc();
  });
  $("#iq-reset").addEventListener("click", () => renderInvoiceEditor(e));
  $("#iq-save").addEventListener("click", async () => {
    const by = await adminName();
    if (by && (await save(by))) await loadOrders();
  });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (!form.reportValidity()) return;
    const by = await adminName();
    if (!by) return;
    const ok = await confirmModal({
      eyebrow: "Generate Invoice",
      title: `Generate ${collect().invoice_number}?`,
      message: "The invoice is finalised with the details shown and can no longer be edited.",
      confirmText: "Generate",
    });
    if (!ok || !(await save(by))) return;
    try {
      await api(`/api/invoice-queue/${e.order_id}/generate`, { method: "POST", body: JSON.stringify({ generated_by: by }) });
      await loadOrders();
    } catch (err) {
      await noticeModal("Generation failed", err.message);
    }
  });
  recalc();
}

$("#add-order")?.addEventListener("click", () => {
  selectedOrderId = null;
  $(".active", $("#order-rows"))?.classList.remove("active");
  renderOrderForm();
  $("#order-detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
});

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

  // Phone / webcam scan: capture, crop and enhance, then upload like a picked file.
  $("[data-scan]", form)?.addEventListener("click", async () => {
    if (!window.Scanner) return;
    const file = await window.Scanner.open();
    if (!file) return;
    if (lbl) lbl.innerHTML = `<strong>${esc(file.name)}</strong>`;
    processSelectedFile(file);
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
showTab(true);
