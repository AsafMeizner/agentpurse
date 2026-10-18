"""Spending policy engine: decides allow / needs_approval / deny for a payment request."""
from dataclasses import dataclass, field
from datetime import datetime, timezone

ALLOW, APPROVAL, DENY = "allow", "needs_approval", "deny"
OVERRIDE_FLAG = "request text tries to override policy"
"""Set by the parser's own pattern check whatever the model says: such a request is denied."""


@dataclass
class Policy:
    monthly_budget: float = 500.0
    per_payment_cap: float = 200.0       # above this: hard deny
    approval_threshold: float = 50.0     # above this: a human must approve
    allowed_categories: set = field(default_factory=lambda: {"office", "software", "shipping", "services"})
    blocked_payees: set = field(default_factory=set)
    allowed_payees: set = field(default_factory=set)  # empty = any payee allowed
    currency: str = "USD"


@dataclass
class Decision:
    verdict: str
    reasons: list

    def to_dict(self):
        return {"verdict": self.verdict, "reasons": self.reasons}


def evaluate(policy: Policy, amount: float, payee: str, category: str, spent_this_month: float,
             currency: str = "USD", risk_flags=None) -> Decision:
    """Hard rules first (deny), then soft rules (approval). Reasons are human readable."""
    deny, review = [], []
    payee_l = payee.strip().lower()
    if amount <= 0:
        deny.append("amount must be positive")
    if currency != policy.currency:
        deny.append(f"currency {currency} not allowed (policy: {policy.currency})")
    if payee_l in {p.lower() for p in policy.blocked_payees}:
        deny.append(f"payee '{payee}' is blocked")
    if policy.allowed_payees and payee_l not in {p.lower() for p in policy.allowed_payees}:
        review.append(f"payee '{payee}' is not on the allow-list")
    if category not in policy.allowed_categories:
        deny.append(f"category '{category}' is not permitted")
    if amount > policy.per_payment_cap:
        deny.append(f"amount {amount:.2f} exceeds per-payment cap {policy.per_payment_cap:.2f}")
    if spent_this_month + amount > policy.monthly_budget:
        deny.append(f"would exceed monthly budget ({spent_this_month + amount:.2f} > {policy.monthly_budget:.2f})")
    if amount > policy.approval_threshold:
        review.append(f"amount {amount:.2f} above auto-approval threshold {policy.approval_threshold:.2f}")
    if OVERRIDE_FLAG in (risk_flags or []):
        # A prompt injection is refused outright, never left for someone to approve by mistake.
        deny.insert(0, "the request tries to override the policy (prompt injection)")
    flags = [f"risk flag: {f}" for f in risk_flags or [] if f != OVERRIDE_FLAG]
    if deny:
        # The flags stay with the verdict: an auditor sees why a request was suspicious too.
        return Decision(DENY, deny + flags)
    review += flags
    if review:
        return Decision(APPROVAL, review)
    return Decision(ALLOW, ["within policy"])


def month_key(ts: datetime | None = None) -> str:
    return (ts or datetime.now(timezone.utc)).strftime("%Y-%m")
