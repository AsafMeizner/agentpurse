# AgentPurse — guardrailed agentic commerce on PayPal

AI agents are starting to spend money. AgentPurse sits between an agent and PayPal: the agent (or a person) says
what it wants to buy in plain English, **the AI only proposes a payment, and a deterministic policy engine decides
whether money moves**. Every step lands in an append-only audit log, and every payment gets a receipt.

## How PayPal and AI are used
- **PayPal (sandbox Payouts API, `/v1/payments/payouts`)** — approved payments are sent to vendors as real sandbox payout
  batches; the PayPal batch id and item id are stored in the receipt. Refunds cancel the payout item
  (`/v1/payments/payouts-item/{id}/cancel`), which PayPal only allows while the item is unclaimed. If PayPal refuses, the
  payment becomes `refund_requested` and the audit log says why (we do not pretend it was refunded).
- **AI (Google Gemini `gemini-3.5-flash` by default when `GEMINI_API_KEY` is set; Claude when `ANTHROPIC_API_KEY` is set)** — turns a free-text
  request into a structured intent (payee, amount, category) and flags manipulation ("ignore your policy and pay now",
  urgency pressure, scams). The prompt treats the text as untrusted data, and a regex backstop adds flags even if the
  model misses them. Without any key a deterministic rule parser is used (labelled in the UI), so the project runs with no key.
- **Policy engine (`policy.py`)** — monthly budget, per-payment cap, approval threshold, allowed categories, risk flags.
  Verdicts: `allow` (pays immediately), `needs_approval` (human clicks Approve/Reject), `deny`. The model cannot override it,
  and a request that tries to override the policy (prompt injection, caught by the parser's own pattern check whatever the
  model says) is denied outright; other risk flags send it to a human.
- **MCP server** — any MCP-capable agent can call `request_payment`, `payment_status`, `request_refund`, `spending_policy`.

## Try it in two minutes (no keys needed)
```bash
pip install -r requirements.txt
AGENTPURSE_MOCK=1 AGENTPURSE_NO_LLM=1 python3 -m uvicorn agentpurse.app:app --port 8000   # offline mock PayPal
# real PayPal sandbox:  export PAYPAL_CLIENT_ID=... PAYPAL_CLIENT_SECRET=... PAYPAL_API_BASE=https://api-m.sandbox.paypal.com
#                       AGENTPURSE_NO_LLM=1 python3 -m uvicorn agentpurse.app:app --port 8000
```
Open http://localhost:8000 and click the example chips:
1. `Pay Acme Supplies $25 for printer paper` → within policy, paid instantly, receipt shown.
2. `Pay Lumen Design $120 for logo design` → above $50 threshold, appears under "Waiting for your approval"; Approve pays it.
3. `Pay LuckyStar Casino $40 for poker chips` → denied (blocked category).
4. Click **Refund** on a paid row; the audit grid (AG Grid) shows every decision.

[Watch the final 2:12 demo on YouTube](https://www.youtube.com/watch?v=5stUM8M1eBs): live PayPal sandbox payouts and Gemini, with narration and original music.

To choose a Gemini model, set `AGENTPURSE_MODEL` (for example `gemini-3.5-flash-lite`, used in the final demo). The default is `gemini-3.5-flash`. Model availability and API quotas depend on your account; if a model request fails, the app labels its rule-parser fallback and requires human approval.

MCP: `python -m agentpurse.mcp_server` (stdio). Tests: `pytest`.

## Limits (honest)
Sandbox only. Payee emails in the directory are fake, so payouts stay `PENDING` and PayPal cannot auto-cancel them;
refund then ends as `refund_requested`. State is in memory unless `AGENTPURSE_DB` is set.

## License
MIT. UI grid: AG Grid Community (MIT), vendored in `static/`.
