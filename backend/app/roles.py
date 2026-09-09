"""To'rt rol — ruxsat jadvali o'rniga.

1.0 da 26 ta ruxsat kodi va rol-ruxsat jadvali bor edi. Amalda faqat ikki xil odam bor:
**boshqaruvchi** (boss, assistant — hamma narsani qiladi) va **ijrochi** (bo'lim boshlig'i,
asosiy bo'lim xodimi — o'z vazifasini oladi va topshiradi). Shu sababli ruxsat kodlari
olib tashlandi: tekshiruv `ctx.is_manager` va "bu vazifa meniki" dan iborat.

Bo'lim boshlig'i va ijrochi huquqda bir xil, lekin ikki xil rol — chunki administratsiyada
va hisobotda alohida ro'yxat bo'lib chiqadi va bo'lim boshlig'i bo'limga bog'lanadi.
"""
from __future__ import annotations

from .models import ASSISTANT, BOSS, HEAD, MANAGERS, PERFORMERS, ROLES, WORKER  # noqa: F401

ROLE_NAMES = {
    "uz": {BOSS: "Boshliq", ASSISTANT: "Assistant", HEAD: "Bo'lim boshlig'i", WORKER: "Ijrochi"},
    "ru": {BOSS: "Руководитель", ASSISTANT: "Ассистент", HEAD: "Начальник отдела", WORKER: "Исполнитель"},
    "en": {BOSS: "Boss", ASSISTANT: "Assistant", HEAD: "Department head", WORKER: "Executor"},
}

# Administratsiyada ikkita alohida oyna: "Bo'limlar" va "Asosiy bo'lim xodimlari".
DEPARTMENT_ROLES = (HEAD,)
MAIN_ROLES = (WORKER,)


def role_name(role: str, lang: str = "uz") -> str:
    return ROLE_NAMES.get(lang, ROLE_NAMES["uz"]).get(role, role)


def is_manager(role: str) -> bool:
    return role in MANAGERS


def is_performer(role: str) -> bool:
    return role in PERFORMERS
