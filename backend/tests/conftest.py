import os
import tempfile
from datetime import date

os.environ["LLM_PROVIDER"] = "fake"
os.environ["ENV"] = "test"
os.environ["MODEL_DIR"] = tempfile.mkdtemp()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import session as db_session  # noqa: E402
from app.db.session import Base  # noqa: E402

_DB_FILE = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
db_session.configure_engine(f"sqlite:///{_DB_FILE}")

from app.main import app  # noqa: E402
from app.seed.demo import DEMO_PASSWORD, generate_demo  # noqa: E402

END = date(2026, 11, 8)


@pytest.fixture(scope="session")
def seeded():
    Base.metadata.create_all(db_session.engine)
    with db_session.SessionLocal() as db:
        info = generate_demo(db, end=END, months=4, seed=11)
    return info


@pytest.fixture(scope="session")
def client(seeded):
    return TestClient(app)


@pytest.fixture
def db(seeded):
    with db_session.SessionLocal() as s:
        yield s


def login(client, email, password=DEMO_PASSWORD) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
