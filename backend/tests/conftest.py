# backend/tests/conftest.py
import copy
import sys
import types
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport

# Make repo root importable so "backend" package resolves
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─────────────────────────────
# Minimal Motor-like fake DB
# ─────────────────────────────
class _InsertOneResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class _UpdateResult:
    def __init__(self, matched_count, modified_count):
        self.matched_count = matched_count
        self.modified_count = modified_count


class _DeleteResult:
    def __init__(self, deleted_count):
        self.deleted_count = deleted_count


class _FindCursor:
    def __init__(self, docs):
        # copy so callers can't mutate storage
        self._docs = [copy.deepcopy(d) for d in docs]

    async def to_list(self, _):
        return [copy.deepcopy(d) for d in self._docs]


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


class FakeCollection:
    def __init__(self):
        # store by _id (string)
        self._store = {}

    async def insert_one(self, doc: dict):
        doc = copy.deepcopy(doc)
        if "_id" not in doc:
            doc["_id"] = uuid.uuid4().hex
        self._store[doc["_id"]] = copy.deepcopy(doc)
        return _InsertOneResult(doc["_id"])

    def find(self, filt=None):
        filt = filt or {}
        docs = [d for d in self._store.values() if _match(d, filt)]
        return _FindCursor(docs)

    async def find_one(self, filt=None):
        filt = filt or {}
        for d in self._store.values():
            if _match(d, filt):
                return copy.deepcopy(d)
        return None

    async def update_one(self, filt, update):
        # only handles {"$set": {...}}
        for _id, d in self._store.items():
            if _match(d, filt):
                if "$set" in update:
                    d.update(update["$set"])
                    self._store[_id] = copy.deepcopy(d)
                    return _UpdateResult(1, 1)
                return _UpdateResult(1, 0)
        return _UpdateResult(0, 0)

    async def delete_one(self, filt):
        for _id, d in list(self._store.items()):
            if _match(d, filt):
                del self._store[_id]
                return _DeleteResult(1)
        return _DeleteResult(0)

    async def delete_many(self, filt):
        count = 0
        if not filt:
            count = len(self._store)
            self._store.clear()
            return _DeleteResult(count)
        for _id, d in list(self._store.items()):
            if _match(d, filt):
                del self._store[_id]
                count += 1
        return _DeleteResult(count)


class FakeDB:
    def __init__(self):
        self.positions = FakeCollection()
        self.tags = FakeCollection()


# ─────────────────────────────
# Pytest fixtures
# ─────────────────────────────


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session")
async def app_fixture():
    """
    Patch the app's database to use the in-memory fake BEFORE importing the app.
    """
    # Provide a lightweight yfinance stub so backend imports succeed without the
    # real dependency being installed in the test environment.
    if "yfinance" not in sys.modules:
        dummy = types.ModuleType("yfinance")

        class _DummyTicker:
            def __init__(self, *args, **kwargs):
                pass

            @property
            def fast_info(self):
                return {}

            @property
            def info(self):
                return {}

            def history(self, *args, **kwargs):
                raise NotImplementedError

        dummy.Ticker = _DummyTicker
        sys.modules["yfinance"] = dummy

    from backend.app import database as dbmod  # import module to patch its globals

    # Drop any real client/db and replace with fake
    fake = FakeDB()
    setattr(dbmod, "client", None)
    setattr(dbmod, "db", fake)

    # Now import the FastAPI app (will see the patched db)
    from backend.app.main import app  # noqa: E402

    return app


@pytest_asyncio.fixture(autouse=True)
async def test_db(app_fixture):
    """
    Clean collections before each test.
    """
    from backend.app.database import db  # this is our FakeDB

    await db.positions.delete_many({})
    await db.tags.delete_many({})
    yield


@pytest_asyncio.fixture(scope="function")
async def async_client(app_fixture):
    transport = ASGITransport(app=app_fixture)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
