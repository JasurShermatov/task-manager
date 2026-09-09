#!/usr/bin/env bash
# SAFF Vazifalar 2.0 — noldan ishga tushirish.
#
#   ./fresh.sh          mahalliy (docker-compose.yml)
#   ./fresh.sh prod     server (docker-compose.prod.yml)
#   ./fresh.sh --empty  sinov ma'lumotisiz (faqat boshliq hisobi)
#
# HAMMA ma'lumot o'chadi: baza, yuklangan fayllar, redis. 1.0 dan qolgani ham.
set -euo pipefail

FILE="docker-compose.yml"
SEED=1
for a in "$@"; do
  case "$a" in
    prod) FILE="docker-compose.prod.yml" ;;
    --empty) SEED=0 ;;
    *) echo "Noma'lum parametr: $a"; exit 1 ;;
  esac
done
DC="docker compose -f $FILE"

if [ ! -f .env ]; then
  echo "XATO: .env yo'q. Avval nusxa oling:"
  echo "  cp .env.example .env    # mahalliy"
  echo "  cp .env.prod.example .env   # server"
  exit 1
fi

# Bot tokenini oldindan tekshiramiz - eng ko'p shu joyda adashiladi.
TOKEN=$(grep -E '^BOT_TOKEN=' .env | head -1 | cut -d= -f2- | tr -d '"'"'"' \r')
if [ -z "${TOKEN}" ] || [[ "${TOKEN}" != *:* ]]; then
  echo "OGOHLANTIRISH: .env dagi BOT_TOKEN bo'sh yoki noto'g'ri ko'rinishda."
  echo "  @BotFather -> /mybots -> botingiz -> API Token"
  echo "  Ko'rinishi: 1234567890:AAH...   (qo'shtirnoqsiz)"
  echo "  Bot ishlamaydi, qolgan hammasi ishlayveradi."
  echo
fi

echo "==> 1/5  To'xtatish va HAMMA ma'lumotni o'chirish"
$DC down -v --remove-orphans

echo "==> 2/5  Qayta qurish"
$DC build

echo "==> 3/5  Bazani 2.0 tuzilmasida qurish"
$DC run --rm api python -m app.reset_db --yes

if [ "$SEED" = "1" ]; then
  echo "==> 4/5  Sinov ma'lumoti (10 bo'lim, 62 xodim, ~360 vazifa)"
  $DC run --rm api python -m app.fake_data --reset
else
  echo "==> 4/5  Sinov ma'lumoti o'tkazib yuborildi (--empty)"
fi

echo "==> 5/5  Ishga tushirish"
$DC up -d

echo
$DC ps
PORT=$(grep -E '^WEB_PORT=' .env | head -1 | cut -d= -f2- | tr -d ' \r')
LOGIN=$(grep -E '^ADMIN_LOGIN=' .env | head -1 | cut -d= -f2- | tr -d ' \r')
[ "$FILE" = "docker-compose.yml" ] && PORT="${PORT:-3000}" || PORT="${PORT:-80}"
echo
echo "Tayyor.  http://localhost:${PORT}"
echo "  boshliq : ${LOGIN:-admin} / .env dagi ADMIN_PASSWORD"
[ "$SEED" = "1" ] && echo "  xodimlar: barchasining paroli 1234"
echo
echo "Loglar:   $DC logs -f api bot"
