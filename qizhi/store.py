"""Task store + tamper-evident audit trail + dept-head approval workflow (in-memory, self-contained).

Deliberately independent of app.store / DATABASE_URL: the public methods are the contract, so the dicts can be
swapped for DB tables later.

Audit trail: append-only, each event stores sha256(prev_hash + canonical_json(event)).
Editing or deleting any past event breaks every later hash and verify_audit() reports where.
"""
import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone

# DEMO identities. Replace with SSO / JWT; the rules below only need (name, role, department).
USERS = {
    "alex":   {"name": "Alex Tan",    "role": "analyst",   "department": "AP"},
    "sam":    {"name": "Sam Lee",     "role": "analyst",   "department": "AP"},
    "priya":  {"name": "Priya Nair",  "role": "dept_head", "department": "Procurement"},
    "warren": {"name": "Warren Ong",  "role": "dept_head", "department": "Warehouse"},
    "fiona":  {"name": "Fiona Koh",   "role": "dept_head", "department": "Finance"},
}
STATUSES = ["open", "in_progress", "awaiting_approval", "resolved"]


class StoreError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.tasks, self.audit_log, self.results, self.counter = {}, [], {}, 0

    def reset(self):
        self.__init__()

    # ------------------------------------------------------------ audit trail
    @staticmethod
    def _hash(prev, ev):
        body = json.dumps({k: v for k, v in ev.items() if k != "hash"}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256((prev + body).encode()).hexdigest()

    def log(self, user, action, task_id=None, invoice_no=None, **details):
        with self.lock:
            prev = self.audit_log[-1]["hash"] if self.audit_log else "GENESIS"
            ev = {"seq": len(self.audit_log) + 1, "ts": now(), "actor": user["name"], "role": user["role"],
                  "department": user["department"], "action": action, "task_id": task_id,
                  "invoice_no": invoice_no, "details": details, "prev_hash": prev}
            ev["hash"] = self._hash(prev, ev)
            self.audit_log.append(ev)
            return ev

    def verify_audit(self):
        prev = "GENESIS"
        for ev in self.audit_log:
            if ev["prev_hash"] != prev or ev["hash"] != self._hash(prev, ev):
                return {"valid": False, "broken_at_seq": ev["seq"], "events": len(self.audit_log)}
            prev = ev["hash"]
        return {"valid": True, "broken_at_seq": None, "events": len(self.audit_log), "head": prev}

    def audit_for(self, task_id=None, invoice_no=None):
        return [e for e in self.audit_log if (task_id is None or e["task_id"] == task_id)
                and (invoice_no is None or e["invoice_no"] == invoice_no)]

    # ------------------------------------------------------------ tasks
    def create_task(self, user, invoice_no, s):
        with self.lock:
            key = f"{invoice_no}|{s['group_key']}"
            existing = next((t for t in self.tasks.values() if t["key"] == key and t["status"] != "resolved"), None)
            if existing:
                return existing, False          # idempotent: re-running a match never duplicates
            self.counter += 1
            tid = f"T-{self.counter:04d}"
            t = {"id": tid, "key": key, "invoice_no": invoice_no, "title": s["title"],
                 "description": s.get("description", ""), "suggested_action": s.get("suggested_action", ""),
                 "department": s.get("department", "AP"), "priority": s.get("priority", "P3"),
                 "impact": s.get("impact", "0"), "type": s.get("type", ""),
                 "discrepancy_ids": s.get("discrepancy_ids", []), "ai_refined": s.get("ai_refined", False),
                 "requires_approval": bool(s.get("requires_approval")), "status": "open", "assignee": None,
                 "created_at": now(), "created_by": user["name"],
                 "due": (datetime.now(timezone.utc) + timedelta(days=s.get("due_in_days", 3))).date().isoformat(),
                 "approval": None}
            self.tasks[tid] = t
            self.log(user, "TASK_SUGGESTED", tid, invoice_no,
                     title=t["title"], priority=t["priority"], department=t["department"],
                     requires_approval=t["requires_approval"], ai_refined=t["ai_refined"])
            return t, True

    def _get(self, tid):
        t = self.tasks.get(tid)
        if not t:
            raise StoreError(f"Task {tid} not found", 404)
        return t

    def update_task(self, user, tid, status=None, assignee=None, note=None):
        with self.lock:
            t = self._get(tid)
            if t["status"] == "awaiting_approval":
                raise StoreError("Task is awaiting dept-head approval; use the decision endpoint.", 409)
            if status:
                if status not in STATUSES or status == "awaiting_approval":
                    raise StoreError("Invalid status (use request-approval to enter approval).", 400)
                if status == "resolved" and t["requires_approval"] and not (
                        t["approval"] and t["approval"]["decision"] == "approved"):
                    raise StoreError("This task needs dept-head approval before it can be resolved.", 409)
                old, t["status"] = t["status"], status
                self.log(user, "STATUS_CHANGED", tid, t["invoice_no"], **{"from": old, "to": status, "note": note})
            if assignee is not None:
                t["assignee"] = assignee or None
                self.log(user, "ASSIGNED", tid, t["invoice_no"], assignee=assignee, note=note)
            return t

    def request_approval(self, user, tid, proposed_resolution):
        with self.lock:
            t = self._get(tid)
            if t["status"] in ("awaiting_approval", "resolved"):
                raise StoreError(f"Cannot request approval while task is {t['status']}.", 409)
            if not proposed_resolution.strip():
                raise StoreError("Describe the proposed resolution (e.g. 'accept +5 units, vendor credit next invoice').")
            t["status"] = "awaiting_approval"
            t["approval"] = {"requested_by": user["name"], "requested_by_id": user["id"], "requested_at": now(),
                             "proposed_resolution": proposed_resolution, "decision": None, "decided_by": None,
                             "decided_at": None, "comment": None}
            self.log(user, "APPROVAL_REQUESTED", tid, t["invoice_no"], department=t["department"],
                     proposed_resolution=proposed_resolution, impact=t["impact"])
            return t

    def decide(self, user, tid, decision, comment):
        with self.lock:
            t = self._get(tid)
            ap = t["approval"]
            if t["status"] != "awaiting_approval" or not ap:
                raise StoreError("Task is not awaiting approval.", 409)
            if user["role"] != "dept_head":
                raise StoreError("Only a department head can approve or reject.", 403)
            if user["department"] != t["department"]:
                raise StoreError(f"Only the {t['department']} department head can decide this task.", 403)
            if user["id"] == ap["requested_by_id"]:
                raise StoreError("You cannot approve your own request (segregation of duties).", 403)
            if decision not in ("approved", "rejected"):
                raise StoreError("decision must be 'approved' or 'rejected'.")
            if decision == "rejected" and not comment.strip():
                raise StoreError("A comment is required when rejecting.")
            ap.update(decision=decision, decided_by=user["name"], decided_at=now(), comment=comment)
            t["status"] = "resolved" if decision == "approved" else "in_progress"
            self.log(user, "APPROVED" if decision == "approved" else "REJECTED", tid, t["invoice_no"],
                     comment=comment, proposed_resolution=ap["proposed_resolution"], impact=t["impact"])
            return t

    def save_result(self, inv_no, result):
        with self.lock:
            self.results[inv_no] = result
