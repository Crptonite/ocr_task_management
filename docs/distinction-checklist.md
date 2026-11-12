# IT2134 Distinction (Grade A ≥ 80%) Checklist

**Weighting:** 85% Individual · 15% Group

| Assessment | Weight | Individual | Group |
| --- | --- | --- | --- |
| **Section A: Proposal Presentation (Wk 5)** | **25%** | A1: UI Prototype (20%) | A2: Project Plan (5%) |
| **Section B: Mock Interview (Wk 7)** | **15%** | B1 Tech (10%) + B2 General (2.5%) + B3 Presence (2.5%) | — |
| **Section C: Technical Review (Wk 13)** | **25%** | C1: Progress Demo & Q&A (20%) | C2: Integrated Walkthrough (5%) |
| **Section D: Final Presentation (Wk 18)** | **35%** | D1: Final Demo & Q&A (20%) + D2: Submission (10%) | D3: Integration & Cloud (5%) |

---

## ⚠️ Critical "Easy-to-Miss" Rules in This Rubric

1. **Commit AI Coding Plans BEFORE Code (D2 – 10% Individual)**
   - Before coding any major feature, commit a markdown plan file (e.g. `docs/plans/<member>-<feature>.md`) or AI chat log to Git **first**, then commit the code after.
2. **Every Member Needs a Clickable UI Flow for Week 5 (A1 – 20% Individual)**
   - A1 grades each member on a clickable prototype (Figma or coded) showing their flows end-to-end, **including error states and empty states**, plus **innovative features beyond the core brief**.
3. **No Dead Code (D2 – 10% Individual)**
   - Remove unused files (such as `legacy/opspilot/`) before final submission.
4. **Full Cloud Hosting Required (D3 – 5% Group)**
   - Both the frontend and FastAPI backend must be live and reachable in the cloud (not just localhost).
5. **Traceable Git History Per Member (D3 – 5% Group)**
   - All 4 members (Aeric, Qizhi, Lucas, Wesley) must commit and open PRs from their own GitHub accounts regularly.

---

## Section-by-Section Grade A Requirements

### Section A: Proposal Presentation (Week 5 — 25%)

#### A1: UI Prototype (20% Individual)
- [ ] All client requirements addressed + **innovative ideas** that add clear value beyond the brief.
- [ ] Every major user flow is clickable end-to-end (coded app or Figma).
- [ ] **Error states** (invalid file type, missing PO, price/qty mismatch, failed extraction) and **empty states** ("No invoice selected", empty queue) are visible and demonstrable.
- [ ] Consistent colours, typography (Montserrat), and Koda styling across all screens.
- [ ] A first-time user can navigate to every key screen without guidance.

#### A2: Group Project Plan (5% Group)
- [ ] State **in-scope** items, **user roles** (Staff, Finance Reviewer, Admin), and **explicitly state out-of-scope items** (e.g., replacing Microsoft Dynamics ERP, handling payroll/shipping customs).
- [ ] Every member has **named, similar-sized tasks**.
- [ ] Project plan shows **milestones and exact dates**, and **all 4 members** can explain the full plan.

---

### Section B: Mock Job Interview (Week 7 — 15%)
- [ ] Submit CV **before** the interview.
- [ ] 5-minute face-to-face interview in **professional attire**.
- [ ] Tailor answers to your group's assigned Job Ad (Groups 1–3: Applied AI & Operations; Groups 4–5: Cloud DevOps; Groups 6–7: Cybersecurity).
- [ ] Give specific examples from this project (e.g., FastAPI matching rules, OCR/LLM validation, pytest suite, UI error handling).
- [ ] **Ask at least one prepared question** at the end of the interview.

---

### Section C: Technical Review (Week 13 — 25%)

#### C1: Progress Demo & Client Q&A (20% Individual)
- [ ] All planned core features working live in the demo and **on schedule**.
- [ ] Explain **why** each technical/design choice was made **and what alternatives were considered** (e.g., why FastAPI over Flask, why regex + LLM fallback over LLM-only, why 2-way/3-way tolerance rules).
- [ ] Show a list of **remaining tasks with exact dates** that fit the Week 18 deadline.
- [ ] Answer probing questions accurately without relying on teammates.

#### C2: Group Walkthrough (5% Group)
- [ ] Demo follows **one continuous storyline** from start to finish (e.g., PO exists → supplier sends invoice PDF → AI extracts → matching flags variance → reviewer checks & exports).
- [ ] Smooth hand-overs linking each speaker's part to the previous part without awkward pauses.
- [ ] **All parts run inside one integrated build** (not 4 separate apps).

---

### Section D: Final Presentation & Submission (Week 18 — 35%)

#### D1: Final Demo & Client Q&A (20% Individual)
- [ ] Every key feature demonstrated end-to-end with zero crashes.
- [ ] Demonstrate **Smart Functions** (AI extraction, mismatch flags, tolerance alerts, task/shortage recommendations) and explain **how each one produces insight or saves user steps**.
- [ ] Demonstrate **Usability, Security, and Performance** measures working live (e.g., file-type/size validation, escaped HTML/XSS prevention, environment variable secrets, response time / token telemetry).
- [ ] Demonstrate **invalid inputs & error handling** live (upload wrong file type, broken PDF, missing fields, negative quantity) with clear error messages.
- [ ] Discuss **trade-offs** (cost vs accuracy, speed vs OCR depth, strict vs tolerance matching) when answering Q&A.

#### D2: Project Submission (10% Individual)
- [ ] **Design artefacts:** Use cases, DB schema, and API docs complete and matching the final code.
- [ ] **AI coding plans:** `.md` plan files or AI chat logs committed to Git **before** the code for every major feature.
- [ ] **Clean code:** Consistent naming/structure, **zero dead code**.
- [ ] **Tests:** Automated `pytest` suite covering both **core flows and edge cases**, all passing.

#### D3: Group Submission (5% Group)
- [ ] **Architecture diagram** and **ER diagram (ERD)** match the delivered system.
- [ ] All 4 members' code integrated into a single working system.
- [ ] Git history shows meaningful, traceable commits from every member.
- [ ] Application **hosted in the cloud** with README covering setup, usage, and deployment.
