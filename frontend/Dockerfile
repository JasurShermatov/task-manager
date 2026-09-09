FROM node:22-alpine AS build
WORKDIR /app
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=$VITE_API_BASE
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-site.conf /etc/nginx/site-common.conf
COPY nginx-tls.conf /etc/nginx/tls.conf.tpl
COPY 40-enable-tls.sh /docker-entrypoint.d/40-enable-tls.sh
RUN chmod +x /docker-entrypoint.d/40-enable-tls.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80 443
