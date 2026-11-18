/* ---------- Wesley: 6a Part 2 SG-to-Vietnam ERP Bridge & Price Masking ---------- */

let bridgeRole = "sg"; // "sg" (Singapore HQ) | "vn" (Vietnam Factory - customer price masked)
let bridgeOrders = [];
let bridgeStats = {};
let selectedBridgeId = null;
let bridgeIncludePending = false;
let bridgeCatalogVisible = false;
let bridgeTransferCatalog = [];

(function injectBridgeStyles() {
  const style = document.createElement("style");
  style.textContent = `
    .bridge-controls { display: flex; flex-wrap: wrap; gap: .65rem; align-items: center; }
    .bridge-role-switch {
      display: inline-flex; border: 1px solid var(--line); border-radius: var(--radius);
      overflow: hidden; background: var(--surface-2);
    }
    .bridge-role-btn {
      border: 0; background: transparent; color: var(--muted); font: inherit;
      font-size: .72rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase;
      padding: .5rem .85rem; cursor: pointer; transition: background .15s, color .15s;
    }
    .bridge-role-btn.active { background: var(--accent); color: var(--accent-ink); }
    .bridge-demo-bar {
      display: flex; flex-wrap: wrap; align-items: center; gap: .5rem;
      margin-bottom: 1.2rem; padding: .75rem 1rem;
      background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius);
    }
    .bridge-demo-bar .sample-label { font-size: .72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .09em; color: var(--muted); margin-right: .25rem; }
    .bridge-stats {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: .8rem; margin-bottom: 1.3rem;
    }
    .bridge-banner {
      padding: .7rem .95rem; border-radius: var(--radius); border: 1px solid var(--line);
      font-size: .8rem; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center; gap: .6rem; flex-wrap: wrap;
    }
    .bridge-banner.sg { background: var(--accent-soft); border-color: var(--accent-border); }
    .bridge-banner.vn { background: var(--warn-bg); border-color: var(--warn-border); }
    .bridge-totals {
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: .65rem; margin: 1rem 0;
    }
    .bridge-totals .sum-card { padding: .65rem .75rem; }
    .bridge-risk-box {
      margin: 1rem 0; padding: .85rem 1rem; border-radius: var(--radius);
      border: 1px solid var(--line); background: var(--surface-2); font-size: .82rem;
    }
    .bridge-risk-box.rush { border-color: var(--bad-border); background: var(--bad-bg); }
    .bridge-risk-box.tight { border-color: var(--warn-border); background: var(--warn-bg); }
    .bridge-risk-box.feasible { border-color: var(--ok-border); background: var(--ok-bg); }
    .bridge-risk-head { display: flex; justify-content: space-between; align-items: center; gap: .5rem; flex-wrap: wrap; margin-bottom: .45rem; }
    .bridge-risk-box ul { margin: .45rem 0 0 0; padding-left: 1.1rem; list-style: disc; display: grid; gap: .25rem; }
    .bridge-risk-box li { border-left: 0; padding-left: 0; font-size: .8rem; }
    .bridge-mapper {
      display: flex; flex-wrap: wrap; gap: .45rem; align-items: center;
      margin-top: .45rem; padding: .45rem .55rem; border-radius: var(--radius);
      background: var(--bad-bg); border: 1px solid var(--bad-border);
    }
    .bridge-mapper input {
      width: 96px; padding: .28rem .45rem; font-size: .78rem;
      border: 1px solid var(--line); border-radius: 4px; background: var(--surface); color: var(--text);
    }
    .bridge-masked-tag {
      display: inline-block; padding: .15rem .45rem; border-radius: 4px;
      font-size: .68rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase;
      background: var(--warn-bg); color: var(--warn); border: 1px solid var(--warn-border);
    }
    .bridge-catalog-drawer {
      margin-top: 1.4rem; padding: 1rem; background: var(--surface);
      border: 1px solid var(--line); border-radius: var(--radius);
    }
    .bridge-empty {
      padding: 1.5rem; border: 1px dashed var(--line); border-radius: var(--radius);
      text-align: center; color: var(--muted); font-size: .85rem;
    }
    @media (max-width: 720px) { .bridge-totals { grid-template-columns: 1fr; } }
  `;
  document.head.appendChild(style);
})();

function bridgeApiUrl(path) {
  return (typeof API === "string" ? API : "") + path;
}

function bridgeRiskPillClass(riskLevel) {
  if (riskLevel === "feasible") return "ok";
  if (riskLevel === "tight") return "needs_attention";
  return "mismatch";
}

function bridgeRiskLabel(riskLevel) {
  if (riskLevel === "feasible") return "Feasible";
  if (riskLevel === "tight") return "Tight buffer";
  return "Rush risk";
}

function renderBridgeStats() {
  const el = $("#bridge-stats");
  if (!el) return;
  const s = bridgeStats || {};
  el.innerHTML = `
    <div class="sum-card"><span>Approved Orders</span><strong>${s.total ?? 0}</strong></div>
    <div class="sum-card ok"><span>VN SOs Converted</span><strong>${s.converted ?? 0}</strong></div>
    <div class="sum-card ${(s.unmapped || 0) > 0 ? "bad" : "ok"}"><span>Unmapped SKUs</span><strong>${s.unmapped ?? 0}</strong></div>
    <div class="sum-card ${(s.rush || 0) > 0 ? "warn" : "ok"}"><span>Rush / Tight Lead Time</span><strong>${s.rush ?? 0}</strong></div>
  `;
}

function renderBridgeTable() {
  const tbody = $("#bridge-rows");
  if (!tbody) return;
  if (!bridgeOrders.length) {
    tbody.innerHTML = `<tr><td colspan="5"><div class="bridge-empty">No approved orders ready for the SG–VN ERP Bridge yet. Approve an order in the Order Queue above or click one of the 1-click demo PO chips.</div></td></tr>`;
    $("#bridge-detail").innerHTML = `<p class="muted">No order selected. Approve an order above or load a demo scenario.</p>`;
    return;
  }

  tbody.innerHTML = bridgeOrders
    .map((b) => {
      const risk = b.lead_time_risk?.risk_level || "feasible";
      const statusBadge = b.converted ? "exported" : b.status;
      const statusText = b.converted ? "VN SO Locked" : label(b.status);
      return `<tr data-bridge-id="${esc(b.order_id)}" class="${b.order_id === selectedBridgeId ? "active" : ""}">
        <td><strong>${esc(b.order_number || b.order_id)}</strong><br /><span class="muted">${esc(b.vn_so_number)}</span></td>
        <td>${esc(b.buyer || "—")}<br /><span class="muted">${esc(b.port || "")}</span></td>
        <td>${b.lines.length} SKU(s)${b.unmapped_count ? `<br /><span class="line-issue">${b.unmapped_count} unmapped</span>` : ""}</td>
        <td><span class="pill ${bridgeRiskPillClass(risk)}">${esc(bridgeRiskLabel(risk))}</span></td>
        <td><span class="pill ${esc(statusBadge)}">${esc(statusText)}</span></td>
      </tr>`;
    })
    .join("");

  $$("tr[data-bridge-id]", tbody).forEach((row) =>
    row.addEventListener("click", () => {
      selectedBridgeId = row.dataset.bridgeId;
      $$("tr.active", tbody).forEach((r) => r.classList.remove("active"));
      row.classList.add("active");
      const chosen = bridgeOrders.find((x) => x.order_id === selectedBridgeId);
      if (chosen) renderBridgeDetail(chosen);
    })
  );

  const selected = bridgeOrders.find((b) => b.order_id === selectedBridgeId) || bridgeOrders[0];
  if (selected) {
    selectedBridgeId = selected.order_id;
    $(`tr[data-bridge-id="${CSS.escape(selectedBridgeId)}"]`, tbody)?.classList.add("active");
    renderBridgeDetail(selected);
  }
}

function renderBridgeDetail(b) {
  const detail = $("#bridge-detail");
  if (!detail || !b) return;
  const masked = b.confidentiality_masked;
  const cur = b.currency || "USD";
  const risk = b.lead_time_risk || {};
  const riskLevel = risk.risk_level || "feasible";

  const roleBanner = masked
    ? `<div class="bridge-banner vn"><span><strong>VIETNAM FACTORY ROLE</strong> — Customer contract prices &amp; SG HQ margins are strictly masked.</span><span class="bridge-masked-tag">Confidentiality Lock</span></div>`
    : `<div class="bridge-banner sg"><span><strong>SINGAPORE HQ ROLE</strong> — Full visibility: Customer Contract Price, Vietnam Transfer Price &amp; HQ Margin.</span><span class="pill ready">SG HQ Access</span></div>`;

  const totalsHtml = masked
    ? `<div class="bridge-totals">
        <div class="sum-card warn"><span>Customer Contract</span><strong>MASKED</strong></div>
        <div class="sum-card"><span>VN Transfer Total</span><strong>${b.transfer_total == null ? "Pending map" : esc(money(b.transfer_total, cur))}</strong></div>
        <div class="sum-card warn"><span>SG HQ Margin</span><strong>MASKED</strong></div>
      </div>`
    : `<div class="bridge-totals">
        <div class="sum-card"><span>Customer Contract</span><strong>${esc(money(b.customer_total ?? 0, cur))}</strong></div>
        <div class="sum-card"><span>VN Transfer Total</span><strong>${b.transfer_total == null ? "Pending map" : esc(money(b.transfer_total, cur))}</strong></div>
        <div class="sum-card ${b.hq_margin_total != null && b.hq_margin_total > 0 ? "ok" : ""}"><span>SG HQ Margin</span><strong>${b.hq_margin_total == null ? "Pending map" : `${esc(money(b.hq_margin_total, cur))} (${b.hq_margin_pct}%)`}</strong></div>
      </div>`;

  const issuesHtml = (b.issues || []).length
    ? `<ul>${b.issues.map((i) => `<li class="${i.level === "error" ? "error" : "warning"}">${esc(i.message)}</li>`).join("")}</ul>`
    : "";

  const linesHtml = (b.lines || [])
    .map((l) => {
      const unmapped = l.mapping_status === "unmapped";
      const mapperHtml = unmapped
        ? `<div class="bridge-mapper">
            <span class="line-issue">Unmapped SKU</span>
            <input type="number" min="0.01" step="0.01" value="${l.suggested_transfer_price ?? ""}" data-map-input="${esc(l.sku)}" aria-label="Transfer price for ${esc(l.sku)}" />
            <button type="button" class="btn btn-accent btn-sm" data-map-sku="${esc(l.sku)}">Map Transfer Price</button>
          </div>`
        : "";
      if (masked) {
        return `<tr class="${unmapped ? "bad" : ""}">
          <td><strong>${esc(l.vn_item_code)}</strong><br /><span class="muted">${esc(l.sku)} · ${esc(l.description || "")}</span><br /><span class="muted">${esc(l.plant)} · ${l.lead_time_days}d</span>${mapperHtml}</td>
          <td class="num">${l.quantity}</td>
          <td class="num">${l.transfer_unit_price == null ? "—" : l.transfer_unit_price.toFixed(2)}</td>
          <td class="num">${l.transfer_amount == null ? "—" : l.transfer_amount.toFixed(2)}</td>
        </tr>`;
      }
      return `<tr class="${unmapped ? "bad" : ""}">
        <td><strong>${esc(l.sku)}</strong> → <span class="muted">${esc(l.vn_item_code)}</span><br /><span class="muted">${esc(l.description || "")}</span>${mapperHtml}</td>
        <td class="num">${l.quantity}</td>
        <td class="num">${l.customer_unit_price == null ? "—" : l.customer_unit_price.toFixed(2)}</td>
        <td class="num">${l.transfer_unit_price == null ? "—" : l.transfer_unit_price.toFixed(2)}</td>
        <td class="num">${l.hq_margin == null ? "—" : `${l.hq_margin.toFixed(2)} (${l.margin_pct}%)`}</td>
      </tr>`;
    })
    .join("");

  const tableHead = masked
    ? `<tr><th>VN BOM / SG SKU</th><th class="num">Qty</th><th class="num">Transfer</th><th class="num">VN Total</th></tr>`
    : `<tr><th>SG SKU → VN BOM</th><th class="num">Qty</th><th class="num">Cust Price</th><th class="num">Transfer</th><th class="num">HQ Margin</th></tr>`;

  const exportButtons = masked
    ? `<button type="button" class="btn btn-outline btn-sm" data-export-csv="vn" ${b.can_export ? "" : "disabled"}>Export VN Masked CSV</button>
       <button type="button" class="btn btn-outline btn-sm" data-export-pdf="vn" ${b.can_export ? "" : "disabled"}>Export VN Masked PDF</button>`
    : `<button type="button" class="btn btn-accent btn-sm" data-export-csv="dual" ${b.can_export ? "" : "disabled"}>Export Dual Navision CSV</button>
       <button type="button" class="btn btn-outline btn-sm" data-export-pdf="dual" ${b.can_export ? "" : "disabled"}>Export Dual PDF Pack</button>
       <button type="button" class="btn btn-outline btn-sm" data-export-csv="sg" ${b.can_export ? "" : "disabled"}>SG HQ CSV</button>
       <button type="button" class="btn btn-outline btn-sm" data-export-csv="vn" ${b.can_export ? "" : "disabled"}>VN Masked CSV</button>
       <button type="button" class="btn btn-outline btn-sm" data-export-pdf="vn" ${b.can_export ? "" : "disabled"}>VN Masked PDF</button>`;

  const convAudit = b.conversion?.converted
    ? `<div class="audit approved"><strong>Vietnam Factory SO Locked</strong> (${esc(b.conversion.vn_so_number)}) by ${esc(b.conversion.converted_by)} on ${esc(fmtTime(b.conversion.converted_at))}</div>`
    : "";

  detail.innerHTML = `
    ${roleBanner}
    <div style="display:flex;gap:.45rem;flex-wrap:wrap;align-items:center">
      <span class="pill ${esc(b.status)}">${esc(label(b.status))}</span>
      ${b.converted ? `<span class="pill exported">VN SO Locked</span>` : ""}
      <span class="pill ${bridgeRiskPillClass(riskLevel)}">${esc(bridgeRiskLabel(riskLevel))}</span>
    </div>
    <h3 style="margin-top:.85rem">${esc(b.vn_so_number)}</h3>
    <p class="muted">SG PO: ${esc(b.order_number || b.order_id)} · ${esc(b.navision_doc_no)} · ${esc(b.buyer || "")}</p>
    <p class="muted">Port: ${esc(b.port)} · Ordered ${esc(b.order_date || "—")} · Deliver ${esc(b.delivery_date || "—")}</p>
    ${totalsHtml}
    ${issuesHtml}
    <div class="bridge-risk-box ${esc(riskLevel)}">
      <div class="bridge-risk-head">
        <strong>Lead-Time &amp; Rush Order Advisor</strong>
        <span class="pill ${risk.ai_used ? "generated" : "ready"}">${risk.ai_used ? `Hybrid AI (${risk.tokens} tok)` : "Rules (0 tok)"}</span>
      </div>
      <p>${esc(risk.headline || "")}</p>
      <p class="muted" style="margin-top:.25rem">Available: ${risk.available_days ?? "—"}d · Required: ${risk.required_days ?? "—"}d (${risk.max_mfg_days ?? "—"}d mfg + ${risk.shipping_buffer_days ?? "—"}d freight · ${risk.total_units ?? 0} units)</p>
      ${risk.ai_brief ? `<p style="margin-top:.45rem"><em>${esc(risk.ai_brief)}</em></p>` : ""}
      <ul>${(risk.recommendations || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
      <div class="actions" style="margin-top:.6rem">
        <button type="button" class="btn btn-outline btn-sm" id="bridge-run-advisor">Refresh Risk Advisor</button>
      </div>
    </div>
    <table><thead>${tableHead}</thead><tbody>${linesHtml}</tbody></table>
    ${convAudit}
    <div class="actions" style="margin-top:1.1rem">
      <button type="button" class="btn btn-solid btn-sm" id="bridge-convert-btn" ${!b.can_convert || b.converted ? "disabled" : ""}>
        ${b.converted ? "Vietnam Factory SO Locked" : "Convert & Lock Vietnam SO"}
      </button>
      ${exportButtons}
    </div>
  `;

  $$("[data-map-sku]", detail).forEach((btn) =>
    btn.addEventListener("click", async () => {
      const sku = btn.dataset.mapSku;
      const input = $(`[data-map-input="${CSS.escape(sku)}"]`, detail);
      const val = Number(input?.value);
      if (!(val > 0)) {
        await noticeModal("Invalid Transfer Price", "Enter a positive Vietnam factory transfer price greater than 0.", "Mapping Error");
        return;
      }
      btn.disabled = true;
      btn.textContent = "Saving...";
      try {
        await api(`/api/erp-bridge/transfer-prices/${encodeURIComponent(sku)}`, {
          method: "PUT",
          body: JSON.stringify({ transfer_price: val, updated_by: "Wesley (ERP Coordinator)" }),
        });
        await loadErpBridge();
      } catch (err) {
        await noticeModal("Mapping Failed", err.message);
      }
    })
  );

  $("#bridge-run-advisor", detail)?.addEventListener("click", async () => {
    const btn = $("#bridge-run-advisor", detail);
    btn.disabled = true;
    btn.textContent = "Analyzing...";
    try {
      const updated = await api(`/api/erp-bridge/orders/${encodeURIComponent(b.order_id)}/advisor`, {
        method: "POST",
        body: JSON.stringify({ role: bridgeRole }),
      });
      bridgeOrders = bridgeOrders.map((x) => (x.order_id === updated.order_id ? updated : x));
      renderBridgeDetail(updated);
    } catch (err) {
      await noticeModal("Advisor Error", err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Refresh Risk Advisor";
    }
  });

  $("#bridge-convert-btn", detail)?.addEventListener("click", async () => {
    const ok = await confirmModal({
      eyebrow: "Convert to Vietnam Factory SO",
      title: `Lock ${b.vn_so_number}?`,
      message: "This prepares the price-masked Vietnam Navision 2013 internal sales order with Engineering BOM codes.",
      confirmText: "Convert & Lock",
    });
    if (!ok) return;
    try {
      const updated = await api(`/api/erp-bridge/orders/${encodeURIComponent(b.order_id)}/convert`, {
        method: "POST",
        body: JSON.stringify({ converted_by: "Wesley (ERP Coordinator)", role: bridgeRole }),
      });
      await loadErpBridge();
      await noticeModal("Vietnam SO Locked", `${updated.vn_so_number} (${updated.navision_doc_no}) is ready for Dual Navision 2013 export.`, "ERP Bridge");
    } catch (err) {
      await noticeModal("Conversion Blocked", err.message, "Validation Error");
    }
  });

  $$("[data-export-csv]", detail).forEach((btn) =>
    btn.addEventListener("click", () => {
      const target = btn.dataset.exportCsv;
      confirmAndDownload(
        bridgeApiUrl(`/api/erp-bridge/orders/${encodeURIComponent(b.order_id)}/export.csv?target=${encodeURIComponent(target)}`),
        `Navision 2013 ${target.toUpperCase()} CSV (${b.order_number || b.order_id})`
      );
    })
  );

  $$("[data-export-pdf]", detail).forEach((btn) =>
    btn.addEventListener("click", () => {
      const target = btn.dataset.exportPdf;
      confirmAndDownload(
        bridgeApiUrl(`/api/erp-bridge/orders/${encodeURIComponent(b.order_id)}/export.pdf?target=${encodeURIComponent(target)}`),
        `Navision 2013 ${target.toUpperCase()} PDF (${b.order_number || b.order_id})`
      );
    })
  );
}

function renderBridgeCatalogDrawer() {
  const wrap = $("#bridge-catalog-drawer");
  if (!wrap) return;
  wrap.hidden = !bridgeCatalogVisible;
  if (!bridgeCatalogVisible) return;
  const rows = bridgeTransferCatalog
    .map(
      (c) => `<tr>
        <td><strong>${esc(c.sku)}</strong></td>
        <td>${esc(c.vn_item_code)}</td>
        <td>${esc(c.name)}<br /><span class="muted">${esc(c.bom_summary)}</span></td>
        <td class="num">${bridgeRole === "vn" ? `<span class="bridge-masked-tag">Masked</span>` : (c.customer_list_price == null ? "—" : Number(c.customer_list_price).toFixed(2))}</td>
        <td class="num">${c.transfer_price == null ? `<span class="line-issue">Unmapped</span>` : Number(c.transfer_price).toFixed(2)}</td>
        <td class="num">${c.lead_time_days}d</td>
      </tr>`
    )
    .join("");
  wrap.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
      <div><h4>Master Transfer Price &amp; Vietnam BOM Table</h4><p class="muted small-note">Reference mapping between SG HQ SKUs and Vietnam Navision 2013 BOM item codes.</p></div>
      <button type="button" class="btn btn-outline btn-sm" id="bridge-close-catalog">Hide</button>
    </div>
    <div class="table-wrap"><table class="table">
      <thead><tr><th>SG SKU</th><th>VN BOM Code</th><th>Item &amp; BOM</th><th class="num">Cust List</th><th class="num">Transfer Price</th><th class="num">Lead Time</th></tr></thead>
      <tbody>${rows}</tbody>
    </table></div>
  `;
  $("#bridge-close-catalog", wrap)?.addEventListener("click", () => {
    bridgeCatalogVisible = false;
    wrap.hidden = true;
    if ($("#bridge-toggle-catalog")) $("#bridge-toggle-catalog").textContent = "Transfer Price Table";
  });
}

function wireBridgeEvents() {
  const sec = $("#ord-bridge");
  if (!sec || sec.dataset.wired) return;
  sec.dataset.wired = "1";

  $$("[data-bridge-role]", sec).forEach((btn) =>
    btn.addEventListener("click", () => {
      bridgeRole = btn.dataset.bridgeRole;
      $$("[data-bridge-role]", sec).forEach((b) => b.classList.toggle("active", b.dataset.bridgeRole === bridgeRole));
      loadErpBridge().catch((err) => noticeModal("ERP Bridge Error", err.message));
    })
  );

  $("#bridge-include-pending")?.addEventListener("change", (e) => {
    bridgeIncludePending = Boolean(e.target.checked);
    loadErpBridge().catch(() => {});
  });

  $("#bridge-refresh-btn")?.addEventListener("click", () => {
    loadErpBridge().catch((err) => noticeModal("Refresh Failed", err.message));
  });

  $("#bridge-toggle-catalog")?.addEventListener("click", () => {
    bridgeCatalogVisible = !bridgeCatalogVisible;
    $("#bridge-toggle-catalog").textContent = bridgeCatalogVisible ? "Hide Transfer Table" : "Transfer Price Table";
    renderBridgeCatalogDrawer();
  });

  $$("[data-bridge-seed]", sec).forEach((btn) =>
    btn.addEventListener("click", async () => {
      const scenario = btn.dataset.bridgeSeed;
      btn.disabled = true;
      try {
        const res = await api(`/api/erp-bridge/seed/${encodeURIComponent(scenario)}?role=${encodeURIComponent(bridgeRole)}`, {
          method: "POST",
        });
        selectedBridgeId = res.order?.order_id || null;
        if (typeof loadOrders === "function") {
          await loadOrders();
        } else {
          await loadErpBridge();
        }
      } catch (err) {
        await noticeModal("Could Not Load Demo PO", err.message);
      } finally {
        btn.disabled = false;
      }
    })
  );
}

async function loadErpBridge() {
  wireBridgeEvents();
  const [res, cat] = await Promise.all([
    api(`/api/erp-bridge/orders?role=${encodeURIComponent(bridgeRole)}&include_pending=${bridgeIncludePending ? "true" : "false"}`),
    api("/api/erp-bridge/transfer-prices"),
  ]);
  bridgeOrders = res.orders || [];
  bridgeStats = res.stats || {};
  bridgeTransferCatalog = cat || [];
  renderBridgeStats();
  renderBridgeTable();
  renderBridgeCatalogDrawer();
}
