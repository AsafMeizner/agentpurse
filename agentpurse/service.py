"""Orchestration: request -> intent -> policy -> (approval) -> PayPal payout -> receipt -> audit."""
import json
import uuid

from . import agent
from .policy import ALLOW, APPROVAL, DENY, Policy, evaluate, month_key
from .store import Store, now


class AgentPurse:
    def __init__(self, paypal, store: Store | None = None, policy: Policy | None = None):
        self.pp, self.store, self.policy = paypal, store or Store(), policy or Policy()

    def request(self, text: str, actor: str = "agent") -> dict:
        intent = agent.parse_request(text)
        pid = self.store.add_payment(request_text=text, payee=intent["payee"], email=intent["email"],
                                     amount=intent["amount"], currency=intent["currency"], category=intent["category"],
                                     memo=intent["memo"], status="evaluating", verdict="", reasons="")
        self.store.log(pid, actor, "requested", {"text": text, "intent": intent})
        d = evaluate(self.policy, intent["amount"], intent["payee"], intent["category"],
                     self.store.spent_this_month(month_key()), intent["currency"], intent["risk_flags"])
        self.store.log(pid, "policy-engine", "decision", d.to_dict())
        status = {ALLOW: "approved", APPROVAL: "awaiting_approval", DENY: "denied"}[d.verdict]
        self.store.update_payment(pid, status=status, verdict=d.verdict, reasons=json.dumps(d.reasons))
        if d.verdict == ALLOW:
            return self._pay(pid, "policy-engine")
        return self.store.get_payment(pid)

    def approve(self, pid: int, who: str = "human") -> dict:
        p = self._must(pid, "awaiting_approval")
        if not p["email"]:
            self.store.log(pid, who, "approve_rejected", "no payee email")
            raise ValueError("payee has no email on file; cannot pay")
        hard = evaluate(self.policy, p["amount"], p["payee"], p["category"], self.store.spent_this_month(month_key()), p["currency"])
        if hard.verdict == DENY:  # budget may have changed since the request
            self.store.update_payment(pid, status="denied", reasons=json.dumps(hard.reasons))
            self.store.log(pid, "policy-engine", "denied_on_approval", hard.to_dict())
            return self.store.get_payment(pid)
        self.store.log(pid, who, "approved")
        return self._pay(pid, who)

    def reject(self, pid: int, who: str = "human") -> dict:
        self._must(pid, "awaiting_approval")
        self.store.update_payment(pid, status="rejected")
        self.store.log(pid, who, "rejected")
        return self.store.get_payment(pid)

    def refund(self, pid: int, who: str = "human") -> dict:
        p = self._must(pid, "paid")
        try:
            res = self.pp.cancel_item(p["paypal_item_id"])
        except Exception as e:  # PayPal only lets UNCLAIMED payout items be cancelled
            self.store.update_payment(pid, status="refund_requested")
            self.store.log(pid, who, "refund_requested", f"PayPal could not cancel automatically: {e}")
            return self.store.get_payment(pid)
        self.store.update_payment(pid, status="refunded")
        self.store.log(pid, who, "refunded", res)
        return self.store.get_payment(pid)

    def _pay(self, pid, actor):
        p = self.store.get_payment(pid)
        ref = f"AP{pid}-{uuid.uuid4().hex[:8]}"
        try:
            r = self.pp.send_payout(p["email"], p["amount"], p["currency"], p["memo"], ref)
        except Exception as e:
            self.store.update_payment(pid, status="failed")
            self.store.log(pid, "paypal", "payout_failed", str(e))
            return self.store.get_payment(pid)
        receipt = {"receipt_no": f"AP-{pid:05d}", "payee": p["payee"], "email": p["email"], "amount": p["amount"],
                   "currency": p["currency"], "memo": p["memo"], "paid_at": now(), "authorized_by": actor,
                   "paypal_batch_id": r["batch_id"], "paypal_item_id": r["item_id"]}
        self.store.update_payment(pid, status="paid", paypal_batch_id=r["batch_id"], paypal_item_id=r["item_id"],
                                  receipt=json.dumps(receipt))
        self.store.log(pid, "paypal", "payout_sent", r)
        return self.store.get_payment(pid)

    def _must(self, pid, status):
        p = self.store.get_payment(pid)
        if not p:
            raise KeyError(f"payment {pid} not found")
        if p["status"] != status:
            raise ValueError(f"payment {pid} is '{p['status']}', expected '{status}'")
        return p
