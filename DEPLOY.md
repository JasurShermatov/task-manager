# Serverga o'rnatish

Toza Ubuntu 22.04/24.04 serverda **~10 daqiqa**. Hozircha IP bilan ishlaydi, domen
kelganda oxirgi bo'limga qaraysiz.

---

## 1. Serverga Docker o'rnatish (bir marta)

```bash
ssh root@SERVER_IP

curl -fsSL https://get.docker.com | sh
docker --version && docker compose version
```

## 2. Kodni olib kelish

```bash
mkdir -p /opt && cd /opt
git clone <REPO_MANZILI> saff
cd /opt/saff
```

## 3. Sozlamalarni to'ldirish

```bash
cp .env.prod.example .env

# Kalitlarni bir buyruq bilan yaratib olasiz - chiqqan qiymatlarni .env ga ko'chiring
for k in JWT_SECRET SERVICE_TOKEN FILE_SIGNING_SECRET WEBHOOK_SECRET; do
  echo "$k=$(openssl rand -hex 32)"
done
echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"

nano .env
```

`.env` da **majburiy** to'ldiriladiganlar:

| Kalit | Nima yoziladi |
|---|---|
| `PUBLIC_URL` | `http://SERVER_IP` (domen kelganda `https://saff.uz`) |
| `POSTGRES_PASSWORD` | yuqorida yaratilgani |
| `JWT_SECRET`, `SERVICE_TOKEN`, `FILE_SIGNING_SECRET`, `WEBHOOK_SECRET` | yuqorida yaratilganlari |
| `ADMIN_PASSWORD` | birinchi kirish paroli |
| `BOT_TOKEN` | @BotFather bergan token |

## 4. Ko'tarish

> **Avval portni tekshiring.** Serverda boshqa loyiha ishlab turgan bo'lishi mumkin:
> ```bash
> ss -tlnp | grep -E ':(80|8080)\s'
> ```
> 80-port band bo'lsa `.env` da `WEB_PORT=8080` qiling va `PUBLIC_URL` ga ham portni qo'shing:
> `PUBLIC_URL=http://SERVER_IP:8080`

```bash
cd /opt/saff
docker compose -f docker-compose.prod.yml up -d --build
```

Birinchi build ~3-5 daqiqa. Keyin holatni ko'ring:

```bash
docker compose -f docker-compose.prod.yml ps
curl -s localhost/healthz          # -> ok
curl -s localhost/api/health       # -> {"ok":true,...}
```

Brauzerda **`http://SERVER_IP`** ni oching va `.env` dagi `ADMIN_LOGIN` / `ADMIN_PASSWORD`
bilan kiring. Kirgach darhol *Sozlash → Profil* dan parolni almashtiring.

## 5. Serverning o'zini yopish (muhim)

Faqat 22 (SSH) va 80 (web) portlar ochiq bo'lsin:

```bash
ufw allow 22/tcp && ufw allow 80/tcp && ufw --force enable
# WEB_PORT ni o'zgartirgan bo'lsangiz o'shani oching:
# ufw allow 8080/tcp
ufw status
```

Postgres va API allaqachon tashqariga chiqarilmagan (`docker-compose.prod.yml` da
ularda `ports` yo'q) — ular faqat konteynerlar ichida ko'rinadi.

---

## 1.0 dan 2.0 ga o'tish (eski baza bo'lsa)

2.0 da ma'lumot tuzilmasi butunlay boshqacha: loyiha / joy / ish turi o'rniga **bo'lim va odam**.
Shuning uchun eski baza ustiga qo'yib bo'lmaydi — server ko'tarilmaydi va nima qilish
kerakligini o'zi aytadi:

```
BAZA ESKI (1.0) — 2.0 ga mos emas.
  yetishmayotgan ustunlar: department_id, position
  ...
```

**Bazani yangidan qurish** (hamma ma'lumot o'chadi):

```bash
# kerak bo'lsa avval zaxira
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U saff saff_tasks > saff-1.0.sql

docker compose -f docker-compose.prod.yml run --rm api python -m app.reset_db --yes
docker compose -f docker-compose.prod.yml up -d
```

`run --rm` ishlatiladi, `exec` emas: API ko'tarilmagan bo'lsa `exec` ishlamaydi.

Mahalliy (`docker-compose.yml`) uchun ham xuddi shunday, faqat `-f` siz:

```bash
docker compose run --rm api python -m app.reset_db --yes
docker compose up -d
```

Eng qisqa yo'l (hamma volume bilan birga o'chadi — fayllar ham):

```bash
docker compose down -v && docker compose up -d --build
```

---

## Sinov ma'lumoti (ixtiyoriy)

Tizimni to'ldirib ko'rsatish uchun:

```bash
docker compose -f docker-compose.prod.yml run --rm api python -m app.fake_data --reset
```

Yaratadi: 10 bo'lim, 62 foydalanuvchi (boshliq + assistant + 10 bo'lim boshlig'i +
50 asosiy bo'lim xodimi), 3 oylik tarix bilan ~360 vazifa. Hamma parol `1234`.
Oxirida o'zini tekshiradi va "Mantiq tekshiruvi: HAMMASI TO'G'RI" deb yozadi.

**Real ishni boshlashdan oldin tozalash:**

```bash
docker compose -f docker-compose.prod.yml run --rm api python -m app.fake_data --wipe
```

Boshliq hisobi va sozlamalar joyida qoladi — qolgani tozalanadi.

---

## Kundalik buyruqlar

```bash
cd /opt/saff

# holat va loglar
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api      # backend
docker compose -f docker-compose.prod.yml logs -f bot      # telegram bot
docker compose -f docker-compose.prod.yml logs --tail 80 api

# yangilanish (kod o'zgargandan keyin)
git pull
docker compose -f docker-compose.prod.yml up -d --build

# qayta ishga tushirish
docker compose -f docker-compose.prod.yml restart api bot

# to'xtatish (ma'lumot saqlanadi)
docker compose -f docker-compose.prod.yml down
```

## Zaxira nusxa (backup)

Kuniga bir marta olishni odat qiling:

```bash
cd /opt/saff
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U saff saff_tasks | gzip > ~/saff-$(date +%F).sql.gz
```

Avtomatlashtirish (har kuni 03:00 da):

```bash
crontab -e
# quyidagi qatorni qo'shing:
0 3 * * * cd /opt/saff && docker compose -f docker-compose.prod.yml exec -T db pg_dump -U saff saff_tasks | gzip > ~/saff-$(date +\%F).sql.gz && find ~ -name 'saff-*.sql.gz' -mtime +14 -delete
```

Tiklash:

```bash
gunzip -c ~/saff-2026-09-08.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U saff -d saff_tasks
docker compose -f docker-compose.prod.yml restart api
```

> Tiklashdan keyin API qayta ishga tushirilishi kerak — u ko'tarilganda vazifa kodi
> hisoblagichini bazadagi holatga moslab oladi.

Fotolar bazada emas, `uploads` volume'ida. Ularni ham nusxalash:

```bash
docker run --rm -v saff_uploads:/data -v ~:/backup alpine \
  tar czf /backup/saff-uploads-$(date +%F).tar.gz -C /data .
```

---

## Bir serverda ikkinchi loyiha bo'lsa

Agar serverda allaqachon nginx 80/443 ni band qilgan boshqa loyiha ishlab tursa, ikki yo'l bor:

**Hozir (tez):** `.env` da `WEB_PORT=8080` — sayt `http://SERVER_IP:8080` da ochiladi.
Ikkala loyiha bir-biriga tegmaydi.

**Domen kelganda (to'g'ri yo'l):** eski nginx'ga bitta server bloki qo'shiladi va u bizning
konteynerga uzatadi — shunda 8080 kerak emas, sertifikat ham eski certbot orqali oladi:

```nginx
server {
    listen 443 ssl;
    server_name vazifa.saff.uz;
    ssl_certificate     /etc/letsencrypt/live/saff.uz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/saff.uz/privkey.pem;
    client_max_body_size 60m;
    location / {
        proxy_pass http://127.0.0.1:8080;      # WEB_PORT
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 180s;
    }
}
```

Keyin `.env` da `PUBLIC_URL=https://vazifa.saff.uz` va `docker compose -f docker-compose.prod.yml up -d api bot`.

## Domen ulanganda (1-2 kundan keyin)

**1.** Domen A-yozuvini serverning IP siga qarating, tarqalishini kuting (`dig saff.uz +short`).

**2.** `frontend/nginx.conf` da:

```nginx
server_name saff.uz www.saff.uz;      # _ o'rniga
```

**3.** `.env` da:

```
PUBLIC_URL=https://saff.uz
```

**4.** `docker-compose.prod.yml` dagi `web` servisiga port va sertifikat papkasini qo'shing:

```yaml
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - certs:/etc/letsencrypt
```

va pastdagi `volumes:` ro'yxatiga `certs:` ni qo'shing.

**5.** Sertifikat oling (bir marta):

```bash
cd /opt/saff
docker compose -f docker-compose.prod.yml stop web
docker run --rm -p 80:80 -v saff_certs:/etc/letsencrypt certbot/certbot \
  certonly --standalone -d saff.uz -d www.saff.uz --agree-tos -m siz@pochta.uz --no-eff-email
```

**6.** `frontend/nginx.conf` ga HTTPS blokini qo'shing va HTTP ni yo'naltiring:

```nginx
server {
    listen 80;
    server_name saff.uz www.saff.uz;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl;
    http2 on;
    server_name saff.uz www.saff.uz;

    ssl_certificate     /etc/letsencrypt/live/saff.uz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/saff.uz/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    add_header Strict-Transport-Security "max-age=31536000" always;

    # --- pastdagi hamma narsa 80-portdagi blokdan ko'chiriladi ---
    root /usr/share/nginx/html;
    index index.html;
    client_max_body_size 60m;
    # ... location /api/ , /assets/ , / bloklari o'zgarishsiz ...
}
```

**7.** Qayta ko'taring va 443 ni oching:

```bash
ufw allow 443/tcp
docker compose -f docker-compose.prod.yml up -d --build web
```

Sertifikat 90 kunda tugaydi — yangilash uchun oyiga bir marta:

```bash
0 4 1 * * docker run --rm -v saff_certs:/etc/letsencrypt certbot/certbot renew --quiet && cd /opt/saff && docker compose -f docker-compose.prod.yml restart web
```

---

## Nimadir ishlamasa

| Alomat | Tekshiruv |
|---|---|
| Sayt ochilmayapti | `docker compose -f docker-compose.prod.yml ps` — hamma servis `Up` bo'lsin |
| Kirishda xato | `logs api` ga qarang; `.env` dagi `ADMIN_LOGIN`/`ADMIN_PASSWORD` faqat **birinchi** ishga tushishda ishlaydi |
| Bot javob bermayapti | `logs bot`; `BOT_TOKEN` to'g'rimi; bir vaqtda ikkinchi nusxa ishlamayaptimi |
| Foto ochilmayapti | `.env` dagi `PUBLIC_URL` serverning haqiqiy manzili bilan bir xilmi |
| «Server xatosi» | `docker compose -f docker-compose.prod.yml logs --tail 80 api` — oxirgi traceback |
