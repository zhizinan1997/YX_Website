FROM nginx:1.27-alpine

COPY gateway/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY gateway/entrypoint.sh /entrypoint.sh
COPY cdn_assets /app/cdn_assets

RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
