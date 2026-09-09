"""Eski (1.0) baza ustiga 2.0 ni ko'tarib bo'lmasligi aniq aytilishi kerak.

Bu holat prodda chiqdi: `create_all` mavjud jadvalga ustun qo'shmaydi, shuning uchun
server "column users.department_id does not exist" deb yiqilardi va sabab tushunarsiz edi.
"""
import pytest
from sqlalchemy import create_engine, text


def _legacy_db(tmp_path):
    """1.0 ga o'xshash baza: users bor, lekin department_id yo'q; loyihalar jadvali bor."""
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    eng = create_engine(url)
    with eng.begin() as c:
        c.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, full_name TEXT, role_id INTEGER)"))
        c.execute(text("CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT)"))
        c.execute(text("CREATE TABLE roles (id INTEGER PRIMARY KEY, code TEXT)"))
    eng.dispose()
    return url


def test_old_database_stops_the_server_with_a_clear_message(tmp_path, monkeypatch, caplog):
    from app import main as app_main
    url = _legacy_db(tmp_path)
    eng = create_engine(url)
    monkeypatch.setattr(app_main, "engine", eng)
    with caplog.at_level("ERROR"):
        with pytest.raises(SystemExit):
            app_main.check_schema()
    msg = caplog.text
    assert "BAZA ESKI" in msg
    assert "department_id" in msg, "qaysi ustun yetishmayotgani aytilishi kerak"
    assert "projects" in msg and "roles" in msg, "eski jadvallar sanab o'tilishi kerak"
    assert "app.reset_db --yes" in msg, "nima qilish kerakligi aytilishi kerak"
    eng.dispose()


def test_empty_database_passes(tmp_path, monkeypatch):
    from app import main as app_main
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    monkeypatch.setattr(app_main, "engine", eng)
    app_main.check_schema()          # xato bermasligi kerak
    eng.dispose()


def test_reset_rebuilds_a_legacy_database(tmp_path, monkeypatch):
    """reset_db 1.0 jadvallarini ham o'chiradi — metadata.drop_all ularni bilmaydi."""
    from sqlalchemy import inspect
    from app import reset_db
    from app.db import Base
    url = _legacy_db(tmp_path)
    eng = create_engine(url)
    monkeypatch.setattr(reset_db, "engine", eng)
    monkeypatch.setattr(reset_db, "SessionLocal", lambda: _Session(eng))

    dropped = reset_db.drop_everything()
    assert {"users", "projects", "roles"} <= set(dropped)
    reset_db.Base.metadata.create_all(eng)
    tables = set(inspect(eng).get_table_names())
    assert "departments" in tables and "tasks" in tables
    assert "projects" not in tables and "roles" not in tables
    cols = {c["name"] for c in inspect(eng).get_columns("users")}
    assert {"role", "position", "department_id"} <= cols
    eng.dispose()


class _Session:
    def __init__(self, eng):
        from sqlalchemy.orm import sessionmaker
        self._s = sessionmaker(bind=eng)()

    def __getattr__(self, k):
        return getattr(self._s, k)
