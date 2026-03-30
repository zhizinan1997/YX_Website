FROM nginx:1.27-alpine

COPY gateway/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY gateway/entrypoint.sh /entrypoint.sh

RUN mkdir -p /app/cdn_assets \
    && chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
