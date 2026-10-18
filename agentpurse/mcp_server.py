"""MCP server: lets any agent (Claude Desktop, etc.) spend through AgentPurse's policy guardrails.
Run: python -m agentpurse.mcp_server   (stdio)"""
import json
import os

from mcp.server.fastmcp import FastMCP

from . import paypal
from .service import AgentPurse
from .store import Store

mcp = FastMCP("agentpurse")
ap = AgentPurse(paypal.from_env(), Store(os.environ.get("AGENTPURSE_DB", "agentpurse.db")))


def _out(p):
    return {k: (json.loads(v) if k in ("reasons", "receipt") and v else v) for k, v in p.items()}


@mcp.tool()
def request_payment(text: str) -> dict:
    """Ask to pay a vendor in plain English, e.g. 'Pay Acme Design $25 at billing@acme.example for logo'.
    The policy engine pays instantly if within policy, holds it for human approval if above the threshold,
    or denies it (blocked category, over cap/budget, prompt-injection flags)."""
    return _out(ap.request(text, actor="mcp-agent"))


@mcp.tool()
def payment_status(payment_id: int) -> dict:
    """Current status, policy reasons and receipt of a payment."""
    p = ap.store.get_payment(payment_id)
    return _out(p) if p else {"error": "not found"}


@mcp.tool()
def request_refund(payment_id: int) -> dict:
    """Ask for a refund of a paid payment (cancels the PayPal payout if still unclaimed)."""
    try:
        return _out(ap.refund(payment_id, who="mcp-agent"))
    except (KeyError, ValueError) as e:
        return {"error": str(e)}


@mcp.tool()
def spending_policy() -> dict:
    """The active spending policy and month-to-date spend."""
    from .policy import month_key
    p = ap.policy
    return {"monthly_budget": p.monthly_budget, "per_payment_cap": p.per_payment_cap,
            "approval_threshold": p.approval_threshold, "categories": sorted(p.allowed_categories),
            "spent_this_month": ap.store.spent_this_month(month_key())}


if __name__ == "__main__":
    mcp.run()
