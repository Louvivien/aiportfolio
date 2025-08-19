# backend/smoke/test_api_smoke.py
import copy

import pytest
from _pytest.monkeypatch import MonkeyPatch
from bson import ObjectId
from fastapi.testclient import TestClient


# ---- Minimal in-memory fake DB compatible with your app ----
class _InsertOneResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class _UpdateResult:
    def __init__(self, matched_count, modified_count):
        self.matched_count, self.modified_count = matched_count, modified_count


class _DeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


def _match(doc, filt):
    if not filt:
        return True
    for k, v in filt.items():
        if isinstance(v, dict) and "$in" in v:
            if doc.get(k) not in set(v["$in"]):
                return False
        else:
            if doc.get(k) != v:
                return False
    return True


class _FindCursor:
    def __init__(self, docs):
        self._docs = [copy.deepcopy(d) for d in docs]

    async def to_list(self, _):
        return [copy.deepcopy(d) for d in self._docs]


class FakeCollection:
    def __init__(self):
        self._store = {}

    async def insert_one(self, doc):
        doc = copy.deepcopy(doc)
        doc.setdefault("_id", ObjectId())
        self._store[doc["_id"]] = copy.deepcopy(doc)
        return _InsertOneResult(doc["_id"])

    def find(self, filt=None):
        docs = [d for d in self._store.values() if _match(d, filt or {})]
        return _FindCursor(docs)

    async def find_one(self, filt=None):
        for d in self._store.values():
            if _match(d, filt or {}):
                return copy.deepcopy(d)
        return None

    async def update_one(self, filt, update):
        for _id, d in self._store.items():
            if _match(d, filt or {}):
                if "$set" in update:
                    d.update(update["$set"])
                    self._store[_id] = copy.deepcopy(d)
                    return _UpdateResult(1, 1)
                return _UpdateResult(1, 0)
        return _UpdateResult(0, 0)

    async def delete_one(self, filt):
        for _id, d in list(self._store.items()):
            if _match(d, filt or {}):
                del self._store[_id]
                return _DeleteResult(1)
        return _DeleteResult(0)

    async def delete_many(self, filt=None):
        if not filt:
            n = len(self._store)
            self._store.clear()
            return _DeleteResult(n)
        n = 0
        for _id, d in list(self._store.items()):
            if _match(d, filt):
                del self._store[_id]
                n += 1
        return _DeleteResult(n)


class FakeDB:
    def __init__(self):
        self.positions = FakeCollection()
        self.tags = FakeCollection()


def test_api_returns_different_values_for_different_symbols():
    import backend.app.main as appmod

    mp = MonkeyPatch()
    try:
        # Patch DB + price fetcher
        appmod.db = FakeDB()

        async def fake_get_prices(symbols):
            table = {"NVDA": 125.0, "SAN.PA": 11.5}
            return {s.upper(): table.get(s.upper(), 0.0) for s in symbols}

        mp.setattr(appmod, "get_prices", fake_get_prices, raising=True)

        client = TestClient(appmod.app)

        # Create positions
        r1 = client.post(
            "/positions",
            json={"symbol": "NVDA", "quantity": 2.0, "cost_price": 100.0, "tags": []},
        )
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["symbol"] == "NVDA"
        assert d1["current_price"] == pytest.approx(125.0)

        r2 = client.post(
            "/positions",
            json={"symbol": "SAN.PA", "quantity": 1.0, "cost_price": 12.0, "tags": []},
        )
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2["symbol"] == "SAN.PA"
        assert d2["current_price"] == pytest.approx(11.5)

        # Read back and verify different prices
        rows = client.get("/positions").json()
        by = {p["symbol"]: p for p in rows}
        assert by["NVDA"]["current_price"] == pytest.approx(125.0)
        assert by["SAN.PA"]["current_price"] == pytest.approx(11.5)

        # Summary sanity check
        s = client.get("/positions/summary").json()
        assert s["total_market_value"] == pytest.approx(250.0 + 11.5)
        assert s["total_unrealized_pl"] == pytest.approx((125 - 100) * 2 + (11.5 - 12) * 1)
    finally:
        mp.undo()
