"""Task suggestions from a project brief (EM Services AI extension).

Owner: Lucas (OCR & AI). Keyword rules for now; swap `suggest_tasks` for an LLM
call later and keep the return shape (list of {"title": str}).
"""

RULES = [
    (("lift", "elevator"), ["Notify residents of lift downtime", "Book lift contractor", "Schedule lift safety inspection"]),
    (("fire", "sprinkler", "extinguisher", "scdf"), ["Check fire extinguisher expiry dates", "Test sprinkler pressure", "Prepare SCDF submission"]),
    (("led", "lighting", "light"), ["Survey existing fittings", "Collect supplier quotes", "Record baseline energy use"]),
    (("permit", "bca", "approval"), ["Prepare permit application", "Chase authority approval"]),
    (("resident", "tenant", "notice"), ["Draft resident notice", "Post notices in lift lobbies"]),
    (("contractor", "vendor", "supplier"), ["Confirm contractor schedule", "Check contractor insurance"]),
    (("inspect", "audit", "survey"), ["Create inspection checklist", "Photograph findings"]),
    (("report", "handover"), ["Draft completion report", "Hold handover walkthrough"]),
]
GENERIC = ["Kick-off meeting with stakeholders", "Set budget and timeline", "Close-out review"]


def suggest_tasks(brief: str, existing_titles: list[str] | None = None, limit: int = 5) -> list[dict]:
    text = brief.lower()
    existing = {t.lower() for t in existing_titles or []}
    picks: list[str] = []
    for keywords, titles in RULES:
        if any(k in text for k in keywords):
            picks.extend(titles)
    picks.extend(GENERIC)
    out: list[dict] = []
    for title in picks:
        if title.lower() not in existing and title not in (s["title"] for s in out):
            out.append({"title": title})
        if len(out) == limit:
            break
    return out
