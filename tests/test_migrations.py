from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from gnss_service import db


def test_migrations_apply_on_empty_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    assert "jobs" in inspect(db.make_engine(url)).get_table_names()
