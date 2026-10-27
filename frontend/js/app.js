// Same origin when served by FastAPI; change if the frontend is hosted separately.
const API = "";

const $ = (sel) => document.querySelector(sel);
const money = (n, cur) => `${cur} ${Number(n).toLocaleString(undefined, { minimumFractionDigits: 2 })}`;

// Theme
$("#theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("koda-theme", next);
});

// Solid nav after scrolling past the hero
const nav = $(".nav");
addEventListener("scroll", () => nav.classList.toggle("scrolled", scrollY > innerHeight * 0.6));

async function getJSON(path) {
  const res = await fetch(API + path);
  if (!res.ok) throw new Error(res.statusText);
  return res.json();
}

function renderStats(invoices) {
  const count = (s) => invoices.filter((i) => i.match.status === s).length;
  const stats = { total: invoices.length, matched: count("matched"), review: count("review"), mismatch: count("mismatch") };
  for (const [key, val] of Object.entries(stats)) document.querySelector(`[data-stat="${key}"]`).textContent = val;
}

function renderDetail(inv) {
  const flags = inv.match.flags.length
    ? `<ul>${inv.match.flags.map((f) => `<li class="${f.level}">${f.message}</li>`).join("")}</ul>`
    : `<p class="muted" style="margin-top:1rem">All lines agree with ${inv.po_number}.</p>`;
  const lines = inv.lines
    .map((l) => `<tr><td>${l.sku}</td><td class="num">${l.qty}</td><td class="num">${l.unit_price.toFixed(2)}</td></tr>`)
    .join("");
  $("#detail").innerHTML = `
    <span class="pill ${inv.match.status}">${inv.match.status}</span>
    <h3 style="margin-top:1rem">${inv.invoice_number}</h3>
    <p class="muted">${inv.supplier} · ${inv.invoice_date}</p>
    ${flags}
    <table><thead><tr><th>SKU</th><th class="num">Qty</th><th class="num">Unit</th></tr></thead><tbody>${lines}</tbody></table>
    <p style="margin-top:1rem" class="num"><strong>${money(inv.total, inv.currency)}</strong></p>`;
}

function renderInvoices(invoices) {
  const tbody = $("#invoice-rows");
  tbody.innerHTML = invoices
    .map(
      (inv, i) => `<tr data-i="${i}">
        <td>${inv.invoice_number}</td><td>${inv.supplier}</td><td>${inv.po_number}</td>
        <td class="num">${money(inv.total, inv.currency)}</td>
        <td><span class="pill ${inv.match.status}">${inv.match.status}</span></td></tr>`
    )
    .join("");
  tbody.querySelectorAll("tr").forEach((row) =>
    row.addEventListener("click", () => {
      tbody.querySelector(".active")?.classList.remove("active");
      row.classList.add("active");
      renderDetail(invoices[row.dataset.i]);
    })
  );
}

function renderOrders(orders) {
  $("#po-cards").innerHTML = orders
    .map(
      (po) => `<div class="card">
        <span class="accent">${po.currency}</span>
        <h4>${po.po_number}</h4>
        <p class="muted">${po.supplier}</p>
        <p class="muted">${po.lines.length} line(s)</p></div>`
    )
    .join("");
}

// Upload
const form = $("#upload-form");
const fileInput = $("#file");
fileInput.addEventListener("change", () => (form.querySelector("label").textContent = fileInput.files[0]?.name || "Choose a file"));
["dragover", "dragleave", "drop"].forEach((evt) =>
  form.addEventListener(evt, (e) => {
    e.preventDefault();
    form.classList.toggle("drag", evt === "dragover");
    if (evt === "drop") {
      fileInput.files = e.dataTransfer.files;
      fileInput.dispatchEvent(new Event("change"));
    }
  })
);
form.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!fileInput.files.length) return;
  const body = new FormData();
  body.append("file", fileInput.files[0]);
  const out = $("#upload-result");
  out.hidden = false;
  out.textContent = "Uploading…";
  try {
    const res = await fetch(API + "/api/invoices/upload", { method: "POST", body });
    out.textContent = JSON.stringify(await res.json(), null, 2);
  } catch (err) {
    out.textContent = "Upload failed: " + err.message;
  }
});

// Init
(async () => {
  try {
    const [invoices, orders] = await Promise.all([getJSON("/api/invoices"), getJSON("/api/purchase-orders")]);
    renderStats(invoices);
    renderInvoices(invoices);
    renderOrders(orders);
  } catch {
    $("#invoice-rows").innerHTML = `<tr><td colspan="5" class="muted">Backend not reachable. Start it with: uvicorn app.main:app --reload</td></tr>`;
  }
})();

