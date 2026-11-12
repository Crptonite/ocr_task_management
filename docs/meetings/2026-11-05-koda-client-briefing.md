# Koda Ltd Client Briefing Notes (SCCCI × NYP)

- **Date:** 5 November 2026
- **Client Speaker:** Ms Caroline Ng (Koda Ltd)
- **NYP Host:** Ms Sun Yuanxin (NYP)

---

## 1. Company & ERP Architecture

- **Current ERP:** **Microsoft Dynamics Navision 2013** (legacy version). Upgrading to Microsoft Dynamics 365 Business Central with built-in AI is currently cost-prohibitive and hard to integrate with external systems.
- **Multi-Entity Operations & Dual Data Entry:**
  - **Koda Ltd (Singapore HQ):** Parent company handling global B2B sales contracts.
  - **Koda Vietnam & Malaysia:** Manufacturing entities (Vietnam is the largest factory with **1,000+ floor workers**).
  - **Commune:** Retail/lifestyle subsidiary (with operations in China).
- **Why Data Is Entered Twice (SG ERP vs Vietnam ERP):**
  - Customer Purchase Orders (POs) arrive at Singapore HQ at the **Customer Sales Contract Price**.
  - Singapore HQ issues an internal PO / Sales Order (SO) to the Vietnam factory at a **Factory Transfer Price**.
  - **Strict Confidentiality Boundary:** Factory and sourcing staff in Vietnam must **never** see the customer contract price (only the factory transfer price) to prevent conflict of interest. Because the two Navision instances are separate entities with different pricing structures, staff manually re-enter the order data.

---

## 2. Business Model & Order Intake (6a Context)

- **B2B Contract Manufacturing (Not B2C):**
  - Koda's core business is B2B wholesale/contract manufacturing for major global furniture retailers and buying agents (e.g., **Pottery Barn, Crate & Barrel, Costco**).
  - Orders do **not** come from `kodaonline.com`.
- **How POs Arrive:**
  1. **Email attachments** (typed English PDFs in each buyer's own format).
  2. **Customer 3rd-party supplier portals** (Koda staff must manually log into different customer portals to download POs).
- **High-SKU Complexity:**
  - Even a modest order (e.g., 50 chairs) can be split across **20–30 different SKUs** with long product descriptions and very similar SKU codes (where a 1-digit typo causes costly production/shipping errors).

---

## 3. Expanded Scope of 6b (AI Invoice & Document Checking)

Caroline clarified that **Problem Statement 6b** covers **multi-document cross-checking across both Finance/Subcon and Shipping workflows**:

1. **Shipping & Commercial Document Cross-Checking (English, Typed PDFs / Excel):**
   - Before a container ships, shipping staff manually cross-check:
     - **Commercial Invoices** (frequently prepared in **Excel outside the ERP** because major buyers require custom invoice formats)
     - **Packing Lists**
     - **Bills of Lading (B/L)** & **Freight Forwarder Invoices**
     - **Customer PO / Internal Factory SO**
   - **Goal:** Zero discrepancies in SKU codes, quantities, unit prices, CBM/carton counts, port of destination, and delivery dates before shipment release.
2. **Vietnam Domestic / Subcontractor ("Subcon") Invoices & Factory Slips (Vietnamese / Bilingual / Handwritten):**
   - Customer-facing documents are in **English** and typed.
   - Local Vietnam supplier/subcontractor invoices (for WIP/sub-assemblies) and factory floor documents (material requisition slips, QC inspection slips) are often in **Vietnamese (or bilingual English–Vietnamese)** and frequently **handwritten** because the 1,000+ factory floor workers do not use computers.

---

## 4. Competitor Benchmark: Why Koda Rejected `File.ai`

- Koda previously evaluated **File.ai** (`file.ai`), which demonstrated strong OCR (including handwriting) and document cross-matching.
- **Why Koda did NOT buy File.ai:**
  - **High minimum volume / subscription package:** File.ai required a high minimum monthly document commitment that Koda's shipping/finance volume did not justify.
- **How Our Solution Wins:**
  - **Pay-per-use / Low Token Cost:** Use lightweight open-source OCR (`pypdf` / `Tesseract`) first and invoke LLM vision/extraction only when needed, with transparent **per-document token cost tracking** and **no expensive minimum package**.

---

## 5. Department-Level User Roles & Approval Workflow

Caroline emphasized that there is **no single cross-department super-approver**; workflows and approvals stay **within each department**:

| Role / Department | Real-World Responsibility at Koda |
| :--- | :--- |
| **Marketing Staff (Vietnam)** | Receives POs, enters SOs, checks SKU/description/qty/destination, and emails customers if details are missing or mismatched. |
| **Engineering Department** | Maintains Bills of Materials (BOM) and product specifications in ERP. |
| **Shipping & Finance Staff** | Cross-checks Commercial Invoices, Packing Lists, Bills of Lading, and Subcon/Supplier Invoices against PO/SO records. |
| **Department Head** | Approves flagged exceptions and oversees turnaround time within their own department. |

---

## 6. Production & Material Planning Realities (6c Context)

- **Why Timber Cannot Be 100% Automated by Standard ERP MRP:**
  - **Organic Material Yield Loss:** Timber has natural knots and defects (e.g., a plank calculated to yield 6 chair legs may only yield 3–4 usable legs).
  - **Oxidation / Tannin Color Shifts:** Older timber stock oxidizes and changes color, so planners cannot blindly mix old and new batches without physical warehouse checks.
  - **Long Lead Times:** Imported timber has a **3–6 month lead time**.
- **Prioritization Rule:** Planners use Excel + physical stock checks and prioritize **major accounts** and **contracts with late-shipment penalty clauses**.

---

## 7. Koda's Core Success Metric & POC Expectations

- **Primary KPI:** **Man-hours saved** (e.g., reducing a 10-hour manual sorting and cross-checking workload to 2 hours) so Koda does not need to increase headcount as Vietnam labor costs rise—while keeping AI running costs significantly lower than the labor hours saved.
- **Approved POC Scope:**
  - A **standalone human-in-the-loop web application** that extracts, cross-checks, highlights discrepancies, and lets staff export ERP-ready CSV/Excel data.
  - **Out of Scope for POC:** Direct live integration into Microsoft Dynamics Navision 2013 and automated logins to external customer supplier portals.
