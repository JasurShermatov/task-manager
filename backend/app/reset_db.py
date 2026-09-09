"""Bazani 2.0 tuzilmasiga qaytadan qurish.

1.0 va 2.0 ma'lumot tuzilmasi butunlay boshqacha (loyiha/joy/ish turi o'rniga bo'lim va odam),
shuning uchun "ustun qo'shish" bilan o'tib bo'lmaydi — jadvallar yangidan quriladi.

    docker compose run --rm api python -m app.reset_db --yes

Diqqat: HAMMA ma'lumot o'chadi. Zaxira kerak bo'lsa avval:

    docker compose exec db pg_dump -U saff saff_tasks > saff-backup.sql
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import inspect, text

from .db import Base, SessionLocal, engine
from .seed import seed


def drop_everything() -> list[str]:
    """Postgres'da butun `public` sxemasi, SQLite'da hamma jadval o'chadi.
    Metadata.drop_all yetmaydi: u faqat 2.0 jadvallarini biladi, 1.0 dan qolganlarini emas."""
    dropped = sorted(inspect(engine).get_table_names())
    with engine.begin() as c:
        if engine.dialect.name == "postgresql":
            c.execute(text("DROP SCHEMA public CASCADE"))
            c.execute(text("CREATE SCHEMA public"))
        else:
            c.execute(text("PRAGMA foreign_keys=OFF"))
            for name in dropped:
                c.execute(text(f'DROP TABLE IF EXISTS "{name}"'))
    return dropped


def build() -> None:
    Base.metadata.create_all(engine)
    if engine.dialect.name == "postgresql":
        with engine.begin() as c:
            c.execute(text("CREATE SEQUENCE IF NOT EXISTS task_code_seq START 1000"))
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="SAFF Vazifalar 2.0 — bazani qaytadan qurish")
    p.add_argument("--yes", action="store_true", help="tasdiqlash (busiz ishlamaydi)")
    args = p.parse_args(argv)

    tables = sorted(inspect(engine).get_table_names())
    if not args.yes:
        print("Bu buyruq HAMMA ma'lumotni o'chiradi.")
        print("Hozirgi jadvallar:", ", ".join(tables) or "(bo'sh)")
        print("\nDavom etish uchun --yes qo'shing:")
        print("  docker compose run --rm api python -m app.reset_db --yes")
        return 1

    dropped = drop_everything()
    print(f"O'chirildi: {len(dropped)} ta jadval" + (f" ({', '.join(dropped)})" if dropped else ""))
    build()
    print("2.0 tuzilmasi qurildi va boshliq hisobi yaratildi.")
    print("Sinov ma'lumoti kerak bo'lsa: python -m app.fake_data --reset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
