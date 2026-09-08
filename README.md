# SAFF Vazifalar nazorati

Qurilish kompaniyasi uchun vazifa boshqaruvi: **vazifa berish → bajarish → dalil bilan tekshirish → yopish**.
Uch kanal emas, ikkitasi: **Web** (ofis) va **Telegram bot** (maydon). Ikkalasi ham bitta API ustida ishlaydi —
raqamlar hamma joyda bir xil.

```
frontend (React 18 + TS + Vite, nginx)  ─┐
                                          ├─→  api (FastAPI + SQLAlchemy 2)  ─→  postgres 16
bot (aiogram 3)  ────────────────────────┘                                   └─→  redis
```

---

## 1. Tez ishga tushirish

```bash
cp .env.example .env      # kalitlarni to'ldiring (pastda)
docker compose up --build
```

| Xizmat | Manzil |
|---|---|
| Web | http://localhost:3000 |
| API (Swagger) | http://localhost:8000/docs |
| Postgres | localhost:5433 |

Birinchi ishga tushishda jadvallar, 6 ta rol, 10 ta ish turi, bitta demo loyiha va **admin** foydalanuvchi
avtomatik yaratiladi (`ADMIN_LOGIN` / `ADMIN_PASSWORD`). **Birinchi kirishdanoq parolni almashtiring.**

## 2. `.env`

| Kalit | Nima uchun |
|---|---|
| `POSTGRES_*` | Baza. `POSTGRES_PORT` — host porti (default 5433, mahalliy postgres bilan urishmasin) |
| `JWT_SECRET` | Access token imzosi. Prodda albatta yangisini qo'ying |
| `SERVICE_TOKEN` | Bot → API xizmat tokeni (bot foydalanuvchi nomidan ish qiladi) |
| `FILE_SIGNING_SECRET` | Foto/hujjat havolalari imzosi (havola 5 daqiqa yashaydi) |
| `ADMIN_LOGIN` / `ADMIN_PASSWORD` | Faqat birinchi ishga tushishda ishlatiladi |
| `PUBLIC_API_URL` | Imzolangan fayl havolalari shu manzil bilan quriladi (nginx orqali `http://host:3000/api`) |
| `BOT_TOKEN` | @BotFather bergan token |
| `BOT_MODE` | `polling` (default) yoki `webhook` |
| `WEBHOOK_URL`, `WEBHOOK_SECRET` | Faqat `webhook` rejimida |
| `WEB_URL` | Botdagi «Web'da ochish» tugmasi uchun |
| `OPENAI_API_KEY` | **Ixtiyoriy.** Ovozli va matnli vazifa berish uchun. Bo'lmasa qolgan hammasi ishlayveradi |
| `TZ_NAME` | Biznes sanalar (default `Asia/Tashkent`). Bazada vaqt UTC da |

## 3. Rollar

| Rol | Doira | Nima qila oladi |
|---|---|---|
| Administrator | tizim | hammasi + foydalanuvchi, rol, ish turi, shablon |
| Loyiha rahbari | loyiha | loyihadagi barcha vazifa, muddat/mas'ul o'zgartirish, ommaviy yaratish, hisobot |
| Prorab | uchastka (blok) | o'z blokida vazifa yaratish/boshlash, kunlik hisobot, foto |
| Bajaruvchi | o'ziga biriktirilgan | faqat o'z vazifasi: boshlash, checklist, foto, izoh |
| Tekshiruvchi | loyiha | qabul/qaytarish. **O'zi bajargan vazifani qabul qila olmaydi** |
| Kuzatuvchi | loyiha | faqat ko'rish |

Ruxsat **har so'rovda serverda** tekshiriladi. Rol ruxsatlari UI dan tahrirlanadi
(*Foydalanuvchilar → Rollar va ruxsatlar*).

## 4. Holat mashinasi

```
Rejada ──▶ Jarayonda ──▶ Tekshiruvda ──▶ Bajarildi
   │            │             │
   │            │             └──▶ Jarayonda (qaytarish, sabab majburiy)
   └──▶ Bekor   └──▶ Bloklangan ──▶ oldingi holatga
```

«Bajarildi» ga o'tish uchun uch shart: **majburiy checklist bajarilgan** · **majburiy foto biriktirilgan** ·
**boshqa odam tasdiqlagan**. Bloklashda sabab katalogdan tanlanadi va izoh majburiy.

## 5. Telegram bot

**Bog'lash:** web'da *Sozlamalar → Telegram bot → Kod olish* → botga `/start` → 6 raqamli kodni yuborish.
Bitta Telegram hisob — bitta foydalanuvchi.

**Botda bor:** `/vazifalarim`, `/hisobot` (hajm + ishchi + foto), `/muammo` (bloklash), `/qidir V-1027`,
`/yangi` (tugmalar orqali vazifa berish), tekshiruvchi uchun qabul/qaytarish, ertalabki 08:00 xulosa,
barcha bildirishnomalar. 22:00–07:00 oralig'ida shoshilinch bo'lmagan xabarlar ovozsiz yuboriladi.

**Ovoz bilan vazifa berish** (rahbar/prorab, `OPENAI_API_KEY` kerak):

1. Rahbar botga ovozli xabar yuboradi.
2. Ovoz matnga o'tadi (`gpt-4o-transcribe`), keyin LLM undan tuzilgan vazifa chiqaradi — sarlavha, muddat,
   muhimlik, joy va **eshitilgan ism**.
3. Ism serverda **fuzzy** solishtiriladi (`rapidfuzz`, o'zbekcha translit farqlari hisobga olinadi:
   «Rustam Erkashev» → «Rustam Ergashev»). Bitta nomzod ≥85% va ikkinchisidan ≥10 ball yuqori bo'lsa —
   avtomatik tanlanadi; aks holda kartochkada **nomzod tugmalari** chiqadi.
4. Bot tasdiqlash kartochkasini ko'rsatadi: `✅ Yuborish` · `✏️ Tahrirlash` · `❌ Bekor`.
   **Yuborish bosilmaguncha bazaga hech narsa yozilmaydi.**

Web'da ham xuddi shu narsa bor: *+ Vazifa → 🎙 Ovoz bilan* (mikrofon brauzerdan yoziladi).

## 6. Testlar

```bash
# backend — 35 ta test, TZ §13 qabul mezonlari bo'yicha
cd backend && pip install -r requirements.txt && pytest tests -q

# bot — i18n to'liqligi, kartochka/klaviatura render, va API bilan jonli oqim
cd bot && pip install -r requirements.txt -r requirements-dev.txt && pytest tests -q

# frontend
cd frontend && npm install && npm run typecheck && npm run build
```

Testlar SQLite'da ishlaydi — Postgres kerak emas.

## 7. Papkalar

```
backend/app/
  models.py        9 jadval
  schemas.py       so'rov/javob sxemalari
  auth.py          JWT, rollar, doira (scope) tekshiruvi
  permissions.py   rol → ruxsat kodlari
  routers/         auth · tasks · admin · templates · reports · misc · ai
  services/
    tasks.py       holat mashinasi, progress, audit, bildirishnoma
    ai.py          ovoz → matn → tuzilgan vazifa + ism moslashtirish
    scheduler.py   08:00 xulosa, muddat eslatmalari, takroriy vazifalar
bot/               aiogram 3: handlerlar, render, i18n (uz/ru/en), outbox worker
frontend/src/      React: Kanban, jadval, vazifa paneli, hisobot, sozlamalar
```

## 8. Eslatmalar

- Vazifa **o'chirilmaydi** — arxivga o'tadi (`is_active=false`). Bajarilgan vazifa umuman o'chirilmaydi.
- Xodim ham o'chirilmaydi — **bloklanadi**; vazifalari va tarixi qoladi, tekshiruv navbati rahbarga o'tadi.
- Bir vaqtda tahrirlash `row_version` bilan qo'riqlanadi → `409 VERSION_CONFLICT`.
- Har bir muhim amal `task_history` ga yoziladi: kim, eski/yangi qiymat, **manba** (web/bot) va `request_id`.
- Fayllar diskda (`uploads` volume), bazada emas. Havolalar imzolangan va 5 daqiqa amal qiladi.
- Zaxira: `pg_dump` ni kunlik cron ga qo'ying va oyiga bir marta tiklashni sinab ko'ring.
