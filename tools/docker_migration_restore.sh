#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

die() {
  log "ERROR: $*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

ensure_safe_dir() {
  local dir="$1"
  [[ -n "$dir" ]] || die "empty directory path"
  [[ "$dir" == /root/yxwebsite/* || "$dir" == /root/yxwebsite ]] || die "refusing unsafe directory: $dir"
}

backup_dir_if_needed() {
  local src="$1"
  local dst_root="$2"
  if [[ -d "$src" ]] && find "$src" -mindepth 1 -print -quit | grep -q .; then
    local label
    label="$(basename "$src")"
    mkdir -p "$dst_root/$label"
    rsync -a "$src/" "$dst_root/$label/"
  fi
}

clear_dir_contents() {
  local dir="$1"
  ensure_safe_dir "$dir"
  mkdir -p "$dir"
  find "$dir" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
}

restore_tar_to_root() {
  local archive="$1"
  [[ -f "$archive" ]] || die "missing archive: $archive"
  tar -xzpf "$archive" -C /
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SNAPSHOT_DIR="${1:-}"
[[ -n "$SNAPSHOT_DIR" ]] || die "usage: $0 /path/to/snapshot-dir"
[[ -d "$SNAPSHOT_DIR" ]] || die "snapshot directory not found: $SNAPSHOT_DIR"

require_cmd docker
require_cmd tar
require_cmd gzip
require_cmd rsync
require_cmd curl

MANIFEST_FILE="$SNAPSHOT_DIR/metadata/manifest.env"
[[ -f "$MANIFEST_FILE" ]] || die "missing manifest file: $MANIFEST_FILE"
# shellcheck disable=SC1090
source "$MANIFEST_FILE"

BACKUP_ROOT="${BACKUP_ROOT:-$YX_ROOT/restore-backups/$(date '+%Y%m%d-%H%M%S')}"
WEBSITE_ENV_FILE="$SNAPSHOT_DIR/metadata/$WEBSITE_CONTAINER.env"
GATEWAY_ENV_FILE="$SNAPSHOT_DIR/metadata/$GATEWAY_CONTAINER.env"
WEBSITE_IMAGE_ARCHIVE="$SNAPSHOT_DIR/artifacts/$WEBSITE_CONTAINER.image.tar.gz"
GATEWAY_IMAGE_ARCHIVE="$SNAPSHOT_DIR/artifacts/$GATEWAY_CONTAINER.image.tar.gz"
DATA_ARCHIVE="$SNAPSHOT_DIR/mounts/${WEBSITE_CONTAINER}.data.tar.gz"
PAGES_ARCHIVE="$SNAPSHOT_DIR/mounts/${WEBSITE_CONTAINER}.pages.tar.gz"
CDN_ARCHIVE="$SNAPSHOT_DIR/mounts/${WEBSITE_CONTAINER}.cdn_assets.tar.gz"

[[ -f "$WEBSITE_ENV_FILE" ]] || die "missing env file: $WEBSITE_ENV_FILE"

log "preparing host directories under $YX_ROOT"
mkdir -p "$WEBSITE_MOUNT_DATA" "$WEBSITE_MOUNT_PAGES" "$WEBSITE_MOUNT_CDN"

log "backing up any existing destination content into $BACKUP_ROOT"
backup_dir_if_needed "$WEBSITE_MOUNT_DATA" "$BACKUP_ROOT"
backup_dir_if_needed "$WEBSITE_MOUNT_PAGES" "$BACKUP_ROOT"
backup_dir_if_needed "$WEBSITE_MOUNT_CDN" "$BACKUP_ROOT"

log "removing any existing containers"
docker rm -f "$WEBSITE_CONTAINER" >/dev/null 2>&1 || true
docker rm -f "$GATEWAY_CONTAINER" >/dev/null 2>&1 || true

log "restoring mounted directory payloads"
clear_dir_contents "$WEBSITE_MOUNT_DATA"
clear_dir_contents "$WEBSITE_MOUNT_PAGES"
clear_dir_contents "$WEBSITE_MOUNT_CDN"
restore_tar_to_root "$DATA_ARCHIVE"
restore_tar_to_root "$PAGES_ARCHIVE"
restore_tar_to_root "$CDN_ARCHIVE"

log "loading migration images"
gunzip -c "$WEBSITE_IMAGE_ARCHIVE" | docker load >/dev/null
if [[ -f "$GATEWAY_IMAGE_ARCHIVE" ]]; then
  log "legacy gateway image archive found; loading for compatibility but not starting it"
  gunzip -c "$GATEWAY_IMAGE_ARCHIVE" | docker load >/dev/null
fi

if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
  log "creating docker network $NETWORK_NAME with subnet $NETWORK_SUBNET"
  docker network create --subnet "$NETWORK_SUBNET" "$NETWORK_NAME" >/dev/null
else
  log "docker network already exists: $NETWORK_NAME"
fi

log "starting website container"
docker run -d \
  --name "$WEBSITE_CONTAINER" \
  --restart unless-stopped \
  --network "$NETWORK_NAME" \
  --network-alias "$WEBSITE_CONTAINER" \
  --env-file "$WEBSITE_ENV_FILE" \
  -p "127.0.0.1:${MAIN_PORT}:8000" \
  -v "$WEBSITE_MOUNT_DATA:/app/data" \
  -v "$WEBSITE_MOUNT_PAGES:/app/pages" \
  -v "$WEBSITE_MOUNT_CDN:/app/cdn_assets" \
  "$WEBSITE_IMAGE_TAG" >/dev/null
docker network connect bridge "$WEBSITE_CONTAINER" >/dev/null 2>&1 || true
log "gateway container is deprecated; restore starts website only"

log "waiting for services to settle"
sleep 5

docker ps -a --filter "name=^/${WEBSITE_CONTAINER}$"
curl -fsS -o /dev/null --max-time 10 "http://127.0.0.1:${MAIN_PORT}/"
curl -fsS -o /dev/null --max-time 10 "http://127.0.0.1:${MAIN_PORT}/admin"

ASSET_FILE="$(find "$WEBSITE_MOUNT_CDN" -type f | head -n 1 || true)"
if [[ -n "$ASSET_FILE" ]]; then
  ASSET_PATH="/cdn_assets/${ASSET_FILE#"$WEBSITE_MOUNT_CDN"/}"
  curl -fsS -o /dev/null --max-time 10 "http://127.0.0.1:${MAIN_PORT}${ASSET_PATH}"
fi

log "restore completed from $SNAPSHOT_DIR"
