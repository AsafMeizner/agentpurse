"""FastAPI app: JSON API + single-page UI. Run: uvicorn agentpurse.app:app"""
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent, paypal
from .service import AgentPurse
from .store import Store

STATIC = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(title="AgentPurse")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
ap = AgentPurse(paypal.from_env(), Store(os.environ.get("AGENTPURSE_DB", ":memory:")))


class Req(BaseModel):
    text: str


class PolicyIn(BaseModel):
    monthly_budget: float
    per_payment_cap: float
    approval_threshold: float


def _fmt(p):
    if p:
        p["reasons"] = json.loads(p["reasons"]) if p.get("reasons") else []
        p["receipt"] = json.loads(p["receipt"]) if p.get("receipt") else None
    return p


def _call(fn, *a):
    try:
        return _fmt(fn(*a))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    pol = ap.policy
    llm = agent.provider()
    return {"mode": "mock" if os.environ.get("AGENTPURSE_MOCK") == "1" else "paypal-sandbox",
            "ai": llm or "rules",
            "policy": {"monthly_budget": pol.monthly_budget, "per_payment_cap": pol.per_payment_cap,
                       "approval_threshold": pol.approval_threshold, "categories": sorted(pol.allowed_categories)},
            "payments": [_fmt(p) for p in ap.store.payments()],
            "audit": ap.store.audit()}


@app.post("/api/request")
def request(r: Req):
    return _call(ap.request, r.text)


@app.post("/api/payments/{pid}/approve")
def approve(pid: int):
    return _call(ap.approve, pid)


@app.post("/api/payments/{pid}/reject")
def reject(pid: int):
    return _call(ap.reject, pid)


@app.post("/api/payments/{pid}/refund")
def refund(pid: int):
    return _call(ap.refund, pid)


@app.put("/api/policy")
def set_policy(p: PolicyIn):
    ap.policy.monthly_budget, ap.policy.per_payment_cap, ap.policy.approval_threshold = \
        p.monthly_budget, p.per_payment_cap, p.approval_threshold
    return state()["policy"]
