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

## 1. Tez ishga tushirish (mahalliy kompyuterda)

```bash
cp .env.example .env      # kalitlarni to'ldiring (pastda)
docker compose up --build
```

| Xizmat | Manzil |
|---|---|
| Web | http://localhost:3000 |
| API (Swagger) | http://localhost:8000/docs |
| Postgres | localhost:5433 |

> **Serverga o'rnatish uchun → [DEPLOY.md](DEPLOY.md)** (prod compose, nginx, backup, domen).

Birinchi ishga tushishda jadvallar, 6 ta rol, 10 ta ish turi va **admin** foydalanuvchi avtomatik
yaratiladi (`ADMIN_LOGIN` / `ADMIN_PASSWORD`). Parolni *Sozlash → Profil* dan almashtiring.

### Sinov ma'lumoti bilan to'ldirish (faker)

Bo'sh tizimni baholash qiyin, shuning uchun real qurilishga o'xshash generator bor.
**Prodda ishlatilmaydi** — faqat sinash va ko'rsatish uchun.

```bash
docker compose -f docker-compose.prod.yml exec api python -m app.fake_data          # to'ldiradi
docker compose -f docker-compose.prod.yml exec api python -m app.fake_data --reset  # tozalab qaytadan
docker compose -f docker-compose.prod.yml exec api python -m app.fake_data --wipe   # FAQAT tozalaydi
```

`--wipe` soxta ma'lumotni olib tashlaydi, admin foydalanuvchi / rollar / ish turlari joyida qoladi —
ya'ni real ishni **toza bazadan** boshlash uchun shu buyruq.

Nima yaratiladi: **12 obyekt** (Yunusobod TJM, Sergeli, Chilonzor BC, Samarqand Plaza, ombor,
poliklinika, maktab, logistika terminali…), blok → qavat → zona daraxti (~250 joy),
**32 xodim** barcha rollarda, **~760 vazifa**, hamda checklist, bog'liqlik, kunlik hisobot,
foto, izoh, tarix, bildirishnoma va takroriy qoidalar — ya'ni **barcha jadval** to'ladi.

Oxirida generator o'zini o'zi tekshiradi: jadval bo'yicha sanoq, holatlar kesimi va mantiq
nazorati (bajarilgan vazifada progress 100 va sana bor; bloklanganida sabab bor; bajaruvchi va
tekshiruvchi bir odam emas; kod takrorlanmagan). Postgres'da vazifa kodi ketma-ketligi ham
tekislanadi — busiz keyingi «yangi vazifa» kod to'qnashuvi bilan xato berardi.

Xodimlar paroli — `1234`: `arustamov` (rahbar), `skarimov` (prorab), `rergashev` (bajaruvchi),
`dtoshmatov` (tekshiruvchi), `mahmedova` (kuzatuvchi).

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
| `MIN_PASSWORD_LEN` | Parol uzunligi (default **4** — ichki tizim). Asosiy himoya: 5 xato urinishdan keyin 15 daqiqa qulf |
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

Ruxsat **har so'rovda serverda** tekshiriladi. Rol ruxsatlari UI dan tahrirlanadi:
*Boshqaruv → Administratsiya → Rollar*.

### Alohida panel yo'q — panel roldan chiqadi

Har bir xodim **bitta va o'sha manzilga** (http://localhost:3000) o'z login/paroli bilan kiradi.
Ilova bitta; chap menyuda kimga nima ko'rinishi rolining ruxsatlaridan avtomatik quriladi.
Kim qaysi bo'limni ko'rishini *Administratsiya → Rol panellari* jadvalidan jonli ko'rish mumkin:

| Bo'lim | Admin | Rahbar | Prorab | Bajaruvchi | Tekshiruvchi | Kuzatuvchi |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| Vazifalar (Doska/Jadval) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Hisobot | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Ommaviy yaratish | ✓ | ✓ | — | — | — | — |
| Loyihalar (daraxt) | ✓ | ✓ | ✓ | — | — | — |
| Shablonlar | ✓ | ✓ | — | — | — | — |
| Ish turlari | ✓ | — | — | — | — | — |
| Telegram bot · Profil | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Xodimlar** (ro'yxat) | ✓ | — | — | — | — | — |
| **Administratsiya** | ✓ | — | — | — | — | — |

*Xodimlar* — superadmin uchun, faqat ko'rish: ism, rol, doira, aloqa va shaxsiy KPI.
**Login/parol u yerda ko'rinmaydi** — parol almashtirish *Administratsiya → Kirish huquqi* da.
Ro'yxatdagi ruxsat faqat menyuda emas — manzilni qo'lda yozib kirishga ham yo'l yopiq.

### Administratsiya (faqat superadmin)

Bitta bo'limda to'rt ish:

- **Kirish huquqi** — xodim qo'shish/tahrirlash, rol va doira berish, **unutilgan parolni yangilash**,
  bloklash/tiklash. Xodim o'z kabinetida parolini almashtirsa ayni o'sha yozuv o'zgaradi —
  ikkita parol bo'lmaydi, **oxirgi versiya ishlaydi**.
- **Rollar** — ruxsat matritsasi (26 kod, 5 guruh). Katakni bosib yoqasiz/o'chirasiz;
  Administrator roli qulflangan.
- **Bot** — bot username'i (kod tegmasdan) va «Botga o'tish» havolasi.
- **Rol panellari** — yuqoridagi jadvalning jonli ko'rinishi.

### Kim kimga vazifa bera oladi

Ikki qoida serverda majburiy (web, bot — hammasi uchun bir xil):

- **Bajaruvchi** — faqat ishni boshlay oladigan odam (`tasks.start`): ishchi, prorab, rahbar.
  Tekshiruvchi yoki kuzatuvchi tanlansa vazifa «rejada» qotib qolardi — endi rad etiladi.
- **Tekshiruvchi** — faqat qabul qila oladigan odam (`tasks.accept`): tekshiruvchi, rahbar, admin.
  Prorab yoki ishchi tanlansa vazifa «tekshiruvda» abadiy osilib qolardi — endi rad etiladi.

Ro'yxatlar (web'dagi tanlash oynasi ham, botdagi tugmalar ham) shu qoida bo'yicha filtrlanadi,
shuning uchun noto'g'ri odamni tanlashning iloji yo'q.

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

**Bog'lash:** web'da *Sozlash → Telegram bot* → **«Botga o'tish»** havolasi → botda `/start` →
web'dagi *Kod olish* tugmasi bergan 6 raqamli kodni botga yuborish.
Bitta Telegram hisob — bitta foydalanuvchi.

Bot manzili kodda emas — bazada (`app_settings.bot_username`). Bot ishga tushganda o'zini
avtomatik ro'yxatdan o'tkazadi, superadmin esa *Administratsiya → Bot* dan istalgan vaqtda
o'zgartira oladi. Botni almashtirsangiz web'dagi havola ham o'zi yangilanadi.

**Bot menyusi rolga qarab quriladi** — har kim faqat o'ziga keraklisini ko'radi:

| Bo'lim | Admin | Rahbar | Prorab | Bajaruvchi | Tekshiruvchi | Kuzatuvchi |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| 📋 Vazifalarim | — | ✓ | ✓ | ✓ | ✓ | — |
| 📷 Kunlik hisobot | — | ✓ | ✓ | ✓ | — | — |
| ⛔ Muammo (bloklash) | — | ✓ | ✓ | ✓ | — | — |
| ➕ Yangi vazifa | ✓ | ✓ | ✓ | — | — | — |
| 🔍 Tekshiruv navbati | — | ✓ | — | — | ✓ | — |
| 📊 Hisobot (KPI) | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| ⏱ Kechikkan · ⛔ Bloklangan | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| 👥 Jamoa | ✓ | — | — | — | — | — |
| 🔎 Qidirish · 🌐 Til · ℹ️ Yordam | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

**Nega superadminda «Vazifalarim» yo'q:** unga hech kim vazifa bermaydi va u tekshiruvchi qilib
tayinlanmaydi, ya'ni bu ro'yxatlar u uchun **doim bo'sh** chiqardi. Uning botdagi ishi — vazifa berish
va raqamlarni kuzatish. Kunlik hisobot ham unga **keladi** (bildirishnoma sifatida), lekin u hisobot
*topshirmaydi*. Kuzatuvchida ham shu sabab «Vazifalarim» olib tashlandi.

Ertalabki 08:00 xulosa, muddat eslatmalari va barcha bildirishnomalar ham shu yerga keladi.
22:00–07:00 oralig'ida shoshilinch bo'lmagan xabarlar ovozsiz yuboriladi.

**Kunlik hisobot kimga boradi:** ishchi botdan (yoki web'dan) hisobot topshirsa — o'sha vazifaning
**prorabi, loyiha rahbari, tekshiruvchisi va superadmin** darhol xabar oladi: hajm, ishchi soni,
izoh va jamlanma («156 / 240 m3»). Xabar Telegramga ham, web'dagi qo'ng'iroqqa ham tushadi.

**Ovoz bilan vazifa berish** (rahbar/prorab/admin, `OPENAI_API_KEY` kerak):

1. Botga **oddiy ovozli xabar** yuboriladi — hech narsani oldindan tanlash shart emas,
   vazifa ustiga bosish ham kerak emas. Shunchaki gapirasiz:
   «Rustam Ergashevga B blok 5-qavatda devor terishni jumagacha topshir, shoshilinch».
2. Ovoz matnga o'tadi (`gpt-4o-transcribe`), keyin LLM undan tuzilgan vazifa chiqaradi — sarlavha,
   muddat, muhimlik, joy, ish turi va **eshitilgan ism**.
3. Ism serverda **fuzzy** solishtiriladi (`rapidfuzz`, o'zbekcha translit farqlari hisobga olinadi:
   «Rustam Erkashev» → «Rustam Ergashev», 95%). Bitta nomzod ≥85% va ikkinchisidan ≥10 ball
   yuqori bo'lsa — avtomatik tanlanadi.
4. **Bir xil ismli ikki odam bo'lsa** hech qachon avtomatik tanlanmaydi — kartochkada nomzod
   tugmalari chiqadi va ular bir-biridan ajralib turadi: rol, obyekt/blok, kerak bo'lsa telefon
   oxirgi 4 raqami (`👤 Aziz Aliyev · Bajaruvchi · …2233`).
5. Bot tasdiqlash kartochkasini ko'rsatadi: `✅ Yuborish` · `✏️ Tahrirlash` · `❌ Bekor`.
   **Yuborish bosilmaguncha bazaga hech narsa yozilmaydi.**

Nomzodlar faqat ishni bajara oladigan odamlardan tanlanadi, tekshiruvchi esa qabul qila
oladiganlardan — ya'ni ovozdan chiqqan vazifa har doim yaratiladi, rad etilmaydi.

Web'da ham xuddi shu narsa bor: *+ Vazifa → 🎙 Ovoz bilan*. Lekin brauzer mikrofoni
**faqat HTTPS da** (yoki localhost'da) ishlaydi — `http://IP` da brauzerning o'zi ruxsat bermaydi.
Domen va sertifikat ulanmaguncha web'da tugma o'rniga shu haqda izoh chiqadi, **botdagi ovoz esa
ishlayveradi** (Telegram audioni o'zi yuboradi, brauzer mikrofoni kerak emas).

## 6. Testlar

```bash
# backend — 62 ta test: TZ §13 qabul mezonlari, rollar, doiralar,
#              bildirishnomalar, administratsiya (sozlama, rol matritsasi, parol)
cd backend && pip install -r requirements.txt && pytest tests -q

# bot — 30 ta test: i18n to'liqligi, render, va handlerlarni jonli API ustida
# rollar kesimida haqiqiy oqim bilan ishlatish (ishchi ish boshlaydi → hisobot →
# muammo → tekshiruvchi qabul qiladi)
cd bot && pip install -r requirements.txt -r requirements-dev.txt && pytest tests -q

# frontend
cd frontend && npm install && npm run typecheck && npm run build
```

Testlar SQLite'da ishlaydi — Postgres kerak emas.

## 7. Papkalar

```
backend/app/
  fake_data.py     sinov uchun soxta baza generatori (--reset / --wipe)
  models.py        10 jadval
  schemas.py       so'rov/javob sxemalari
  auth.py          JWT, rollar, doira (scope) tekshiruvi
  permissions.py   rol → ruxsat kodlari
  routers/         auth · tasks · admin · templates · reports · misc · ai
  services/
    tasks.py       holat mashinasi, progress, audit, bildirishnoma
    ai.py          ovoz → matn → tuzilgan vazifa + ism moslashtirish
    scheduler.py   08:00 xulosa, muddat eslatmalari, takroriy vazifalar
bot/               aiogram 3: handlerlar, render, i18n (uz/ru/en), outbox worker
frontend/src/      React: Kanban, jadval, vazifa paneli, hisobot, loyihalar,
                   xodimlar, administratsiya, sozlamalar
```

## 8. Eslatmalar

- Vazifa **o'chirilmaydi** — arxivga o'tadi (`is_active=false`). Bajarilgan vazifa umuman o'chirilmaydi.
- Xodim ham o'chirilmaydi — **bloklanadi**; vazifalari va tarixi qoladi, tekshiruv navbati rahbarga o'tadi.
- Bir vaqtda tahrirlash `row_version` bilan qo'riqlanadi → `409 VERSION_CONFLICT`.
- Har bir muhim amal `task_history` ga yoziladi: kim, eski/yangi qiymat, **manba** (web/bot) va `request_id`.
- Fayllar diskda (`uploads` volume), bazada emas. Havolalar imzolangan va 5 daqiqa amal qiladi.
- Zaxira: `pg_dump` ni kunlik cron ga qo'ying va oyiga bir marta tiklashni sinab ko'ring.
