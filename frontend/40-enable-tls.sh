#!/bin/sh
# nginx:alpine ishga tushishda /docker-entrypoint.d/ dagi skriptlarni o'zi bajaradi.
#
# Sertifikat bor bo'lsa - HTTPS blokini yoqamiz, yo'q bo'lsa tegmaymiz.
# Shu tartibda sertifikatsiz ham konteyner muammosiz ko'tariladi (aks holda nginx
# "cannot load certificate" deb yiqilardi va sayt umuman ochilmasdi).
set -e
if [ -s /etc/nginx/certs/origin.pem ] && [ -s /etc/nginx/certs/origin.key ]; then
  cp /etc/nginx/tls.conf.tpl /etc/nginx/conf.d/tls.conf
  echo "TLS yoqildi: certs/origin.pem topildi"
else
  echo "TLS yoqilmadi: certs/origin.pem yo'q - sayt HTTP'da ishlaydi"
fi
