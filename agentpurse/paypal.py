"""PayPal sandbox client (Payouts API) with an in-process mock for tests/offline use."""
import os
import time
import uuid

import httpx


class PayPalError(Exception):
    pass


class PayPalClient:
    def __init__(self, client_id=None, secret=None, base=None):
        self.id = client_id or os.environ["PAYPAL_CLIENT_ID"]
        self.secret = secret or os.environ["PAYPAL_CLIENT_SECRET"]
        self.base = base or os.environ.get("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")
        if "sandbox" not in self.base:
            raise PayPalError("AgentPurse only runs against the PayPal sandbox")
        self._tok, self._exp = None, 0
        self.http = httpx.Client(timeout=30)

    def _token(self):
        if not self._tok or time.time() > self._exp - 60:
            r = self.http.post(f"{self.base}/v1/oauth2/token", auth=(self.id, self.secret),
                               data={"grant_type": "client_credentials"})
            if r.status_code != 200:
                raise PayPalError(f"auth failed: {r.status_code}")
            j = r.json()
            self._tok, self._exp = j["access_token"], time.time() + j["expires_in"]
        return self._tok

    def _req(self, method, path, **kw):
        r = self.http.request(method, self.base + path, headers={"Authorization": f"Bearer {self._token()}"}, **kw)
        if r.status_code >= 400:
            raise PayPalError(f"{method} {path}: {r.status_code} {r.text[:300]}")
        return r.json() if r.content else {}

    def send_payout(self, email, amount, currency, note, ref):
        """Pay a vendor from the sandbox merchant balance. `ref` makes the batch idempotent."""
        body = {"sender_batch_header": {"sender_batch_id": ref, "email_subject": "Payment from AgentPurse",
                                        "email_message": note[:200]},
                "items": [{"recipient_type": "EMAIL", "amount": {"value": f"{amount:.2f}", "currency": currency},
                           "receiver": email, "note": note[:200], "sender_item_id": ref}]}
        j = self._req("POST", "/v1/payments/payouts", json=body)
        batch = j["batch_header"]["payout_batch_id"]
        d = self._req("GET", f"/v1/payments/payouts/{batch}")
        item = d["items"][0]["payout_item_id"] if d.get("items") else None
        return {"batch_id": batch, "item_id": item, "status": d["batch_header"]["batch_status"]}

    def item_status(self, item_id):
        return self._req("GET", f"/v1/payments/payouts-item/{item_id}").get("transaction_status")

    def cancel_item(self, item_id):
        """Reversal path for unclaimed payouts: cancel the item and return the funds."""
        return self._req("POST", f"/v1/payments/payouts-item/{item_id}/cancel")


class MockPayPal:
    def __init__(self):
        self.items = {}

    def send_payout(self, email, amount, currency, note, ref):
        iid = "MOCK" + uuid.uuid4().hex[:10].upper()
        self.items[iid] = "UNCLAIMED"
        return {"batch_id": "MOCKB" + ref[-6:], "item_id": iid, "status": "PENDING"}

    def item_status(self, item_id):
        return self.items[item_id]

    def cancel_item(self, item_id):
        self.items[item_id] = "RETURNED"
        return {"transaction_status": "RETURNED"}


def from_env():
    if os.environ.get("AGENTPURSE_MOCK") == "1":
        return MockPayPal()
    return PayPalClient()
