from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from gnss_service import db, models  # noqa: F401
from gnss_service.main import app

DATA = Path(__file__).parent / "data"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    engine = db.make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    db.Base.metadata.create_all(engine)
    monkeypatch.setattr(db, "SessionLocal", sessionmaker(bind=engine, expire_on_commit=False))
    return TestClient(app)


@pytest.fixture(scope="session")
def nav_bytes():
    return (DATA / "samsung_nav.nav.rnx").read_bytes()


@pytest.fixture(scope="session")
def obs_bytes():
    return (DATA / "my_data_3.obs").read_bytes()
