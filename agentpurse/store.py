"""SQLite ledger + append-only audit log."""
import json
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS payments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, request_text TEXT, payee TEXT, email TEXT,
  amount REAL, currency TEXT, category TEXT, memo TEXT, status TEXT, verdict TEXT, reasons TEXT,
  paypal_batch_id TEXT, paypal_item_id TEXT, receipt TEXT);
CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, payment_id INTEGER, actor TEXT, event TEXT, detail TEXT);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self.db.executescript(SCHEMA)

    def add_payment(self, **kw) -> int:
        kw.setdefault("created", now())
        with self.lock:
            cur = self.db.execute(f"INSERT INTO payments({','.join(kw)}) VALUES({','.join('?' * len(kw))})", list(kw.values()))
            self.db.commit()
            return cur.lastrowid

    def update_payment(self, pid, **kw):
        with self.lock:
            self.db.execute(f"UPDATE payments SET {','.join(k + '=?' for k in kw)} WHERE id=?", [*kw.values(), pid])
            self.db.commit()

    def get_payment(self, pid):
        r = self.db.execute("SELECT * FROM payments WHERE id=?", (pid,)).fetchone()
        return dict(r) if r else None

    def payments(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM payments ORDER BY id DESC")]

    def spent_this_month(self, month: str) -> float:
        r = self.db.execute("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE status IN ('paid') AND created LIKE ?",
                            (month + "%",)).fetchone()
        return float(r["s"])

    def log(self, payment_id, actor, event, detail=None):
        with self.lock:
            self.db.execute("INSERT INTO audit(ts,payment_id,actor,event,detail) VALUES(?,?,?,?,?)",
                            (now(), payment_id, actor, event, json.dumps(detail) if detail is not None else ""))
            self.db.commit()

    def audit(self):
        return [dict(r) for r in self.db.execute("SELECT * FROM audit ORDER BY id DESC")]
