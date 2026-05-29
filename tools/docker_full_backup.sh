#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE" >&2
}

die() {
  log "ERROR: $*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

BACKUP_ROOT="${BACKUP_ROOT:-/湖南元芯传感官网每日自动备份}"
WEBSITE_CONTAINER="${WEBSITE_CONTAINER:-yx-website}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-yx-gateway}"
KEEP_COUNT="${KEEP_COUNT:-2}"
DATE_TIME="$(date '+%Y-%m-%d_%H-%M-%S')"
BACKUP_DIR="${BACKUP_ROOT}/${DATE_TIME}"
LOG_FILE="${BACKUP_DIR}/backup.log"
BACKUP_STATUS=0
CONTAINERS=("$WEBSITE_CONTAINER" "$GATEWAY_CONTAINER")

require_cmd docker
require_cmd tar
require_cmd gzip
require_cmd find
require_cmd xargs

mkdir -p "$BACKUP_DIR"

log "starting docker full backup"
log "backup root: $BACKUP_ROOT"
log "backup dir: $BACKUP_DIR"
log "keep count: $KEEP_COUNT"

for container in "${CONTAINERS[@]}"; do
  log "processing container: $container"

  if ! docker container inspect "$container" >/dev/null 2>&1; then
    log "container not found, skipping: $container"
    if [[ "$container" == "$WEBSITE_CONTAINER" ]]; then
      BACKUP_STATUS=1
    fi
    continue
  fi

  CONTAINER_DIR="$BACKUP_DIR/$container"
  mkdir -p "$CONTAINER_DIR"

  docker inspect "$container" > "$CONTAINER_DIR/${container}_inspect.json" 2>>"$LOG_FILE" || BACKUP_STATUS=1
  docker export "$container" | gzip -1 > "$CONTAINER_DIR/${container}_filesystem.tar.gz" || BACKUP_STATUS=1

  IMAGE_NAME="$(docker inspect --format='{{.Config.Image}}' "$container" 2>/dev/null || true)"
  if [[ -n "$IMAGE_NAME" ]]; then
    SAFE_IMAGE_NAME="$(printf '%s' "$IMAGE_NAME" | sed 's#[/:]#_#g')"
    docker save "$IMAGE_NAME" | gzip -1 > "$CONTAINER_DIR/${SAFE_IMAGE_NAME}_image.tar.gz" || BACKUP_STATUS=1
  else
    log "failed to resolve image name for $container"
    BACKUP_STATUS=1
  fi

  docker inspect "$container" \
    --format='{{range .Mounts}}{{println .Source "=>" .Destination}}{{end}}' \
    > "$CONTAINER_DIR/${container}_mounts.txt" 2>>"$LOG_FILE" || BACKUP_STATUS=1

  while IFS= read -r src; do
    [[ -n "$src" ]] || continue
    if [[ ! -e "$src" ]]; then
      log "mount source missing, skipping: $src"
      BACKUP_STATUS=1
      continue
    fi
    SAFE_SRC_NAME="$(printf '%s' "$src" | sed 's#^/##' | sed 's#[/: ]#_#g')"
    REL_SRC="${src#/}"
    tar -czpf "$CONTAINER_DIR/mount_${SAFE_SRC_NAME}.tar.gz" -C / "$REL_SRC" 2>>"$LOG_FILE" || BACKUP_STATUS=1
  done < <(docker inspect "$container" --format='{{range .Mounts}}{{println .Source}}{{end}}' 2>/dev/null || true)
done

find "$BACKUP_DIR" -type f -exec ls -lh {} \; > "$BACKUP_DIR/backup_files.txt" 2>>"$LOG_FILE" || true

if [[ "$BACKUP_STATUS" -eq 0 ]]; then
  printf 'success\n' > "$BACKUP_DIR/backup_success.flag"
  log "backup finished successfully"
else
  printf 'failed\n' > "$BACKUP_DIR/backup_failed.flag"
  log "backup finished with failures"
fi

if [[ "$BACKUP_STATUS" -eq 0 ]]; then
  mapfile -t old_backups < <(
    find "$BACKUP_ROOT" -mindepth 2 -maxdepth 2 -name 'backup_success.flag' -printf '%T@ %h\n' 2>/dev/null \
      | sort -n \
      | head -n -"${KEEP_COUNT}" \
      | cut -d' ' -f2-
  )

  for old_backup in "${old_backups[@]}"; do
    [[ -n "$old_backup" ]] || continue
    [[ -d "$old_backup" ]] || continue
    log "removing old backup: $old_backup"
    rm -rf "$old_backup"
  done
fi

log "docker full backup task finished"
