"""Serverdan parol qo'yish — web ishlamay qolsa ham ishlaydigan zaxira yo'l.

    docker compose -f docker-compose.prod.yml run --rm api \\
        python -m app.set_password axmad Axmad30

Nima qiladi:
  * loginni katta-kichik harfga qaramasdan topadi;
  * parolni bcrypt bilan xeshlab qo'yadi (ochiq saqlanmaydi);
  * eski sessiyalarni yopadi va kirish urinishlari qulfini ochadi;
  * oxirida o'sha parol bilan tekshirib ko'radi — "qo'ydim, lekin kirmayapti"
    degan holat qolmasin.

Loginni ko'rish uchun parolsiz chaqiring:  python -m app.set_password --list
"""
from __future__ import annotations

import sys

from sqlalchemy import func, select

from .auth import hash_password, validate_password_strength, verify_password
from .db import SessionLocal
from .models import RefreshToken, User
from .redis_client import attempts_clear
from .routers.auth import attempt_prefix


def _list(db) -> int:
    rows = db.scalars(select(User).order_by(User.id)).all()
    print(f"{'id':>4}  {'login':<16} {'rol':<16} {'faol':<5} ism")
    for u in rows:
        print(f"{u.id:>4}  {u.login:<16} {u.role:<16} {'ha' if u.is_active else 'yo`q':<5} {u.full_name}")
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    db = SessionLocal()
    try:
        if not argv or argv[0] in ("--list", "-l"):
            return _list(db)
        if len(argv) < 2:
            print("Ishlatilishi:  python -m app.set_password <login> <yangi parol>")
            print("Loginlar ro'yxati:  python -m app.set_password --list")
            return 2

        login, password = argv[0].strip().lower(), argv[1]
        u = db.scalar(select(User).where(func.lower(User.login) == login))
        if not u:
            print(f"XATO: '{login}' degan login yo'q. Ro'yxat: python -m app.set_password --list")
            return 1

        validate_password_strength(password)
        u.password_hash = hash_password(password)
        for rt in db.scalars(select(RefreshToken).where(RefreshToken.user_id == u.id,
                                                        RefreshToken.revoked.is_(False))):
            rt.revoked = True
        attempts_clear(attempt_prefix(u.login))
        db.commit()
        db.refresh(u)

        # O'zimizni tekshiramiz: parol rostdan yozildimi.
        if not verify_password(password, u.password_hash):
            print("XATO: parol saqlanmadi. Bazaga yozish muammosi bo'lishi mumkin.")
            return 1
        print(f"Tayyor. {u.full_name} ({u.role}) endi shu bilan kiradi:")
        print(f"  login : {u.login}")
        print(f"  parol : {password}")
        print("Eski sessiyalar yopildi, qulf ochildi.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
