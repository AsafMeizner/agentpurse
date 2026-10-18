# AgentPurse — Devpost write-up (draft)

**Tagline:** Let AI agents spend money through PayPal, inside guardrails a human controls.

## Inspiration
Agents can now shop and pay, but nobody wants to hand an LLM an unlimited card. A prompt-injected invoice or a hallucinated amount is a real loss. We wanted agentic commerce where the model proposes and a deterministic policy decides.

## What it does
You describe a purchase in plain language ("Pay Lumen Design $120 for a logo redesign"). Gemini turns it into a structured intent (payee, amount, category, risk flags). A deterministic policy engine then decides: auto-approve (within budget, cap and category), hold for human approval (above a threshold), or deny (blocked category, over hard cap, over monthly budget, payee not in directory). Approved payments are sent with the PayPal Payouts API; every step is written to an audit log shown in an AG Grid table, with receipts and a refund (cancel unclaimed payout) button. An MCP server exposes the same guarded tools to any other agent.

## How we built it
Python/FastAPI, vanilla JS UI with AG Grid Community, PayPal REST (OAuth + Payouts, sandbox), Gemini for intent parsing, MCP server over stdio. 12 tests pass (policy, service, API). The final narrated demo uses gemini-3.5-flash-lite; the configurable default is gemini-3.5-flash. No key is needed to run: a labelled rule-based parser is used when no model key is present. Model failures are labelled and require human approval.

Final demo (public, 2:12): https://www.youtube.com/watch?v=5stUM8M1eBs

## Key design choice
The LLM never moves money. Its output is untrusted input to a policy engine; a regex backstop adds injection flags even if the model misses them; approvals re-check the budget at approval time.

## Challenges
Sandbox card checkout needs buyer approval and the sandbox merchant cannot process cards, so we built on Payouts, which an agent can run autonomously. PayPal only cancels UNCLAIMED payout items, so refunds fall back to a logged "refund requested" state when cancel is impossible.

## What's next
Invoicing for refunds on claimed payments, per-agent policies, Slack approvals.

## PayPal + AI use
PayPal: OAuth2, Payouts create/get/cancel (sandbox). AI: Gemini parses and risk-flags requests; MCP lets external agents act through the guardrails.
