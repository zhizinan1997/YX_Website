#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

WEBSITE_CONTAINER="${WEBSITE_CONTAINER:-yx-website}"

log "开始重启 Docker 容器"
log "网站容器: $WEBSITE_CONTAINER"

for container in "$WEBSITE_CONTAINER"; do
  if docker container inspect "$container" >/dev/null 2>&1; then
    log "正在重启容器: $container"
    docker restart "$container"
    log "容器已重启: $container"
  else
    log "警告: 容器不存在，跳过: $container"
  fi
done

log "Docker 容器重启完成"
