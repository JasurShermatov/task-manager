# SAFF Vazifalar nazorati 2.0

Boshliq odamlarga vazifa beradi, ular **dalil bilan** topshiradi, boshliq qabul qiladi.
Ikki kanal: **Telegram bot** (kundalik ish) va **Web** (hisobot, administratsiya).
Ikkalasi bitta API ustida — raqamlar hamma joyda bir xil.

```
frontend (React 18 + TS + Vite, nginx)  ─┐
                                          ├─→  api (FastAPI + SQLAlchemy 2)  ─→  postgres 16
bot (aiogram 3)  ────────────────────────┘                                   └─→  redis
```

---

## 1. Noldan ishga tushirish

```bash
cp .env.example .env      # kalitlarni to'ldiring (pastda)
./fresh.sh                # tozalaydi, quradi, sinov ma'lumoti bilan ishga tushiradi
```

`fresh.sh` **hamma ma'lumotni o'chiradi** (baza, yuklangan fayllar, redis) va 2.0 tuzilmasida
qaytadan quradi — noldan sinash uchun. Sinov ma'lumotisiz: `./fresh.sh --empty`.
Serverda: `./fresh.sh prod`.

| Xizmat | Manzil |
|---|---|
| Web | http://localhost:3000 |
| API (Swagger) | http://localhost:8000/docs |
| Postgres | localhost:5433 |

Kirish: `.env` dagi `ADMIN_LOGIN` / `ADMIN_PASSWORD`. Sinov xodimlarining paroli `1234`.

> Serverga o'rnatish → **[DEPLOY.md](DEPLOY.md)**

### Qo'lda

```bash
docker compose run --rm api python -m app.reset_db --yes      # bazani 2.0 da qayta qurish
docker compose run --rm api python -m app.fake_data --reset   # sinov ma'lumoti
docker compose run --rm api python -m app.fake_data --wipe    # faqat tozalash
docker compose up -d --build
```

`run --rm` ishlatiladi, `exec` emas: API ko'tarilmagan bo'lsa `exec` ishlamaydi.

**Sinov ma'lumoti:** 10 bo'lim, 62 foydalanuvchi (boshliq + assistant + 10 bo'lim boshlig'i +
50 asosiy bo'lim xodimi), uch oylik tarix bilan ~360 vazifa — vaqtida bajarilgani, kechikkani,
bajarilmagani va qaytarilgani aralash, hisobot darhol ko'rinsin uchun. Oxirida o'zini tekshiradi.

### Ishga tushmasa

| Belgi | Sabab va yechim |
|---|---|
| `BAZA ESKI (1.0)` | 1.0 dan qolgan baza. `./fresh.sh` yoki `reset_db --yes` |
| `BOT TOKENI NOTO'G'RI` | `.env` dagi `BOT_TOKEN` eskirgan. @BotFather → `/mybots` → API Token |
| Web ochiladi, login ishlamaydi | API ko'tarilmagan: `docker compose logs api` |
| `TelegramConflictError` yoki botda «Kod noto'g'ri» | **Shu token bilan ikkinchi bot ishlayapti** (ko'pincha serverdagi eski nusxa). Ikkinchisi endi o'zi kutib turadi (pastda), birinchisi to'xtaganda o'zi ishga tushadi |
| Botda «Server bilan aloqa uzildi» | API bir zumga javob bermadi. Hisob bog'liqligicha qoladi — qaytadan kod kiritish shart emas |

---

## 2. Sozlamalar (`.env`)

| Kalit | Nima |
|---|---|
| `POSTGRES_*` | Baza nomi, foydalanuvchi, parol |
| `JWT_SECRET`, `SERVICE_TOKEN`, `FILE_SIGNING_SECRET` | Tasodifiy kalitlar: `openssl rand -hex 32` |
| `ADMIN_LOGIN`, `ADMIN_PASSWORD` | Birinchi boshliq hisobi |
| `BOT_TOKEN` | @BotFather bergan token |
| `PUBLIC_API_URL` | Fayl havolalari shu manzil bilan imzolanadi |
| `OPENAI_API_KEY` | **Ixtiyoriy.** Ovozli vazifa uchun. Bo'lmasa qolgani ishlayveradi |
| `MIN_PASSWORD_LEN` | Parol uzunligi (default 4 — ichki tizim; himoya: 5 xatodan keyin 15 daqiqa qulf) |
| `TZ_NAME` | Muddat va hisobot vaqti (default `Asia/Tashkent`) |

---

## 3. Tuzilma va rollar

Boshliq va assistant tepada, **huquqda teng**. Ulardan ikki tomonga shox ketadi:
o'nga yaqin tashqi bo'lim (har birida boshliq; ularning ishchilari platformada yo'q) va
bitta asosiy bo'lim (~50 ijrochi, to'g'ridan-to'g'ri boshliqqa qaraydi).

| Rol | Nechta | Vazifa beradi | Qabul qiladi | Administratsiya | Hisobot |
|---|---|:-:|:-:|:-:|:-:|
| `boss` | 1 | hammaga | ✓ | ✓ | ✓ |
| `assistant` | 1–2 | hammaga | ✓ | ✓ | ✓ |
| `bolim_boshligi` | ~10 | — | — | — | — |
| `ijrochi` | ~50 | — | — | — | — |

Boshliq va assistant bir-biriga ham vazifa bera oladi. Bo'lim boshlig'i va ijrochi huquqda
bir xil; ikki xil rol — chunki administratsiyada va hisobotda alohida ro'yxat bo'lib chiqadi.

**Boshliqning yagona ustunligi:** *assistant hisoblarini faqat u boshqaradi* — ochadi,
tahrirlaydi, parolini almashtiradi, bloklaydi. Assistant na yangi assistant ocha oladi,
na boshliqqa tegadi, na birovni assistantlikka ko'tara oladi. Pastdagi hamma xodim
kesimida esa ikkalasi to'liq teng. Server har so'rovda tekshiradi (`BOSS_ONLY`),
web'da «Assistantlar» oynasi assistantga umuman ko'rinmaydi.

**Rol ≠ lavozim.** Rol faqat "qaysi tugmani bosa oladi"ni belgilaydi — to'rtta va ko'paymaydi.
Lavozim (Buxgalter, Ta'minotchi…) — erkin matn, huquq bermaydi: hisobotda, filtrda va ovozli
vazifada odamni topishda ishlatiladi.

Bir bo'limda bitta boshliq bo'ladi (server ikkinchisini rad etadi). Ijrochida bo'lim bo'lmaydi —
u asosiy bo'lim xodimi.

---

## 4. Vazifa

Uch maydon: **Kimga · Nima · Qachon**. Muddat sana + soat; soat aytilmasa 18:00.
Ustiga ixtiyoriy izoh va fayl.

```
Yangi ──▶ Boshladim ──▶ Topshirdim ──▶ Qabul qilindi
  │       (ixtiyoriy)   (dalil shart)
  └──▶ Bekor            └──▶ Qayta qil (sabab majburiy) ──▶ Boshladim
```

- **Topshirishda dalil majburiy** — kamida bitta rasm yoki fayl.
  *Istisno:* boshliq bilan assistant **bir-biriga** bergan vazifada dalil shart emas —
  ular ko'pincha bir-biriga savol beradi («shartnoma qanday bo'ldi?»), bunday ishning
  rasmi bo'lmaydi. Xohlasa baribir fayl qo'sha oladi. Qoida bitta joyda:
  `services/tasks.proof_required`; API `needs_proof` bilan aytadi, web va bot shunga qaraydi.
- **Qaytarilgandan keyin eski dalil hisobga olinmaydi** — yangisi talab qilinadi.
- Qaytarish sababi izoh bo'lib qoladi, ijrochi nimani tuzatishni ko'radi.
- Muddat surilsa `original_due_at` saqlanadi va necha marta surilgani hisoblanadi.
- «Muammo» degan alohida holat yo'q — ijrochi izoh yozadi, u boshliqqa darhol boradi.
- **O'z ishini o'zi qabul qilmaydi.** Assistant boshliqqa vazifa bersa, uni assistant qabul
  qiladi (va aksincha). O'ziga o'zi qo'ygan vazifa bundan mustasno — uni yopadigan boshqa
  odam yo'q.

---

## 5. Eslatma dvigateli

Muddat qanchalik yaqin bo'lsa, eslatma shuncha tez-tez boradi. Vazifa topshirilgan zahoti to'xtaydi.

| Muddatgacha | Kuniga | Soatlar |
|---|---|---|
| 4 kun va undan ko'p | 1 | 09:00 |
| 1–3 kun | 2 | 09:00, 17:00 |
| Bugun tugaydi | 3 | 09:00, 13:00, muddatdan 2 soat oldin |
| Muddat o'tdi | 3 | 09:00, 13:00, 17:00 |

Boshliq va assistantga alohida: muddatdan **+1 soat** o'tganda darhol bitta xabar va har kuni
ertalab kechikkanlar ro'yxati. **21:00–08:00 orasida hech narsa yuborilmaydi.**

Soatlar `.env` da emas, *Sozlamalar* da o'zgartiriladi (`app_settings.reminder_hours`).
Takrorlanmaslik bazadagi unique kalit bilan ta'minlangan — server qayta ko'tarilsa ham
bir xil eslatma ikki marta ketmaydi.

---

## 6. Telegram bot

**Bog'lash:** web'da *Sozlamalar → Telegram → Kod olish* → botda `/start` → 6 raqamli kodni yuborish.

Menyu roldan quriladi:

| Boshliq / assistant | Bo'lim boshlig'i / ijrochi |
|---|---|
| ➕ Yangi vazifa (ovoz yoki matn) | 📋 Vazifalarim |
| 📋 Vazifalarim · ✅ Topshirish | ✅ Topshirish |
| 🟡 Topshirilgan · ⏰ Kechikkan | 🌐 Til |
| 📊 Hisobot · 👥 Odamlar | |
| 🌐 Til | |

«Vazifalarim» va «Topshirish» **hammada** bor: boshliq bilan assistant bir-biriga vazifa
bera oladi, demak ularning ham topshiradigan ishi bo'ladi. Ro'yxatdagi har bir kartochkada
o'sha zahoti «Boshladim / Topshirish» tugmasi turadi — qaysinisini xohlasa o'shani tanlaydi.

**Tasdiqlash kartochkasida «✅ Yuborish» har doim turadi.** Biror maydon to'lmagan bo'lsa
tugma yo'qolib qolmaydi — bosilganda nima yetishmayotgani aytiladi va o'sha qadam ochiladi.

**Topshirish uch qadam:** vazifani tanlash → nima qilindi → rasm/fayl → «Tayyor».
Dalilsiz yuborib bo'lmaydi.

**Xabarning o'zida tugmalar:** kimdir topshirsa, boshliqqa rasm bilan xabar keladi va o'sha
xabarda «✅ Qabul qildim / ↩️ Qayta qil» turadi — ro'yxat ochish shart emas.

**Bitta tokenga bitta bot.** Telegram bir tokenga bitta ulanish beradi. Ikkinchi nusxa
ishga tushsa, yangilanishlar ikkiga bo'linadi va odam «kod noto'g'ri», «hisob bog'lanmagan»
degan xabarlarni ko'radi — go'yo bot uzilib qolgandek. Shuning uchun ijozat (lease) API'da
saqlanadi: birinchi ishga tushgani ishlaydi, ikkinchisi jim kutadi va birinchisi to'xtagan
zahoti **o'zi** ishga tushadi. Hech narsa qo'lda qilinmaydi.

**Bog'lanish uzilmaydi.** API qayta ko'tarilayotganda bot «hisobingizni bog'lang» demaydi —
oxirgi ma'lum holatni ishlatadi va «biroz kuting» deydi. Bog'lanish faqat odam o'zi
*Sozlamalar → Telegram → Uzish* qilganda uziladi.

**Ovozli vazifa** (`OPENAI_API_KEY` bo'lsa): gapirasiz → bot kartochka chiqaradi → «Yuborish».
Xato bo'lsa «Tahrirlash» — vazifa oddiy matn bo'lib chiqadi, nusxa olib tuzatasiz va qaytarasiz.
Sana gap bilan tushuniladi: «ertaga», «ertaga kechgacha», «3 kun», «15.09.2026 14:00».
Ism topilmasa taxmin qilinmaydi — tugma bo'lib chiqadi.

---

## 7. Web

| Sahifa | Kim ko'radi | Ichida |
|---|---|---|
| Bosh sahifa | boshliq, assistant | Kechikkan · Tekshiruvda · Bugun tugaydi · Ochiq · Foiz |
| Vazifalar | boshliq, assistant | Ro'yxat, filtr (odam, bo'lim, holat), qidiruv, kartochka |
| Hisobot | boshliq, assistant | Hafta/oy/yil, foiz, odam kesimi, Excel va CSV |
| Administratsiya | boshliq, assistant | **Bo'limlar**, **Asosiy bo'lim xodimlari**, **Assistantlar** (oxirgisi faqat boshliqqa) |
| Vazifalarim | **hammaga** | Faqat o'ziga berilgan vazifalar, dalil bilan topshirish |
| Sozlamalar | hammaga | Profil, parol, Telegram, eslatma soatlari |

**Kimga berish** bitta uzun ro'yxat emas, ikki ustun: chapda *bo'lim boshliqlari*, o'ngda
*boshqaruvchilar va ijrochilar*, tepasida qidiruv. 60 dan ortiq odam bo'lgani uchun bitta
ro'yxat cho'zilib ketardi.

**O'lchamlar.** Katta ekranda matn va tugmalar kattalashadi (1200px dan keng — 15px,
1700px dan keng — 16px), telefonda esa ixchamlashadi va ikki ustun biri ostiga ikkinchisi
tushadi. Bitta joyda ham gorizontal aylantirish bo'lmaydi.

Ruxsat **har so'rovda serverda** tekshiriladi — manzilni qo'lda yozib kirishga ham yo'l yopiq.

---

## 8. Hisobot

| Ko'rsatkich | Qanday hisoblanadi |
|---|---|
| Berilgan | Shu davrda berilgan vazifalar |
| Vaqtida | Muddatdan oldin topshirilgan va qabul qilingan |
| Kechikib bajarildi | Muddatdan keyin topshirilgan, lekin qabul qilingan |
| Bajarilmadi | Muddat o'tgan, hali topshirilmagan |
| Jarayonda | Muddati kelmagan yoki qabul kutilmoqda |
| Qaytarilgan | Necha marta «Qayta qil» bo'lgani |
| O'rtacha kechikish | Kechikkanlarning o'rtacha kun soni |
| **Foiz** | `vaqtida ÷ berilgan × 100` |

`berilgan = vaqtida + kechikib + bajarilmagan + jarayonda` — hisobot o'zini tekshiradi.
Bekor qilinganlar hisobga kirmaydi. Yuklab olish: **Excel** va **CSV**, web'da ham, botda ham.

---

## 9. Ishlab chiqish

```bash
# testlar
cd backend && python -m pytest -q     # 50 test
cd bot     && python -m pytest -q     # 30 test

# frontend
cd frontend && npm ci && npm run typecheck && npm run build
```

Vaqt qoidasi: **domen vaqti mahalliy** (`app/clock.py`, Asia/Tashkent), **JWT va refresh UTC**.
Domen kodi `datetime.utcnow()` ni chaqirmaydi — faqat `clock` ni.

Baza: 10 jadval — `departments`, `users`, `refresh_tokens`, `tasks`, `task_files`,
`task_comments`, `task_history`, `notifications`, `telegram_link_codes`, `app_settings`.

XLSX eksporti tashqi kutubxonasiz (`app/services/xlsx.py`) — har muhitda ishlaydi va sinaladi.
