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

write_container_env_file() {
  local container="$1"
  local output="$2"
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container" > "$output"
}

tar_mount_dir() {
  local src_dir="$1"
  local output="$2"
  [[ -d "$src_dir" ]] || die "mount directory not found: $src_dir"
  local rel_src="${src_dir#/}"
  tar -czpf "$output" -C / "$rel_src"
}

require_cmd docker
require_cmd tar
require_cmd gzip
require_cmd sha256sum

YX_ROOT="${YX_ROOT:-/root/yxwebsite}"
SNAPSHOT_ROOT="${SNAPSHOT_ROOT:-$YX_ROOT/migration_snapshots}"
NETWORK_NAME="${NETWORK_NAME:-yx-net}"
NETWORK_SUBNET="${NETWORK_SUBNET:-172.20.0.0/16}"
WEBSITE_CONTAINER="${WEBSITE_CONTAINER:-yx-website}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-yx-gateway}"
WEBSITE_MOUNT_DATA="${WEBSITE_MOUNT_DATA:-$YX_ROOT/data}"
WEBSITE_MOUNT_PAGES="${WEBSITE_MOUNT_PAGES:-$YX_ROOT/pages}"
WEBSITE_MOUNT_CDN="${WEBSITE_MOUNT_CDN:-$YX_ROOT/cdn_assets}"
MAIN_PORT="${MAIN_PORT:-2026}"
TIMESTAMP="${TIMESTAMP:-$(date '+%Y%m%d-%H%M%S')}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-$SNAPSHOT_ROOT/$TIMESTAMP}"
ARTIFACT_DIR="$SNAPSHOT_DIR/artifacts"
METADATA_DIR="$SNAPSHOT_DIR/metadata"
MOUNT_DIR="$SNAPSHOT_DIR/mounts"
WEBSITE_SNAPSHOT_IMAGE="${WEBSITE_SNAPSHOT_IMAGE:-yx-migration/yx-website:$TIMESTAMP}"
GATEWAY_SNAPSHOT_IMAGE="${GATEWAY_SNAPSHOT_IMAGE:-yx-migration/yx-gateway:$TIMESTAMP}"

docker container inspect "$WEBSITE_CONTAINER" >/dev/null 2>&1 || die "container not found: $WEBSITE_CONTAINER"
HAS_GATEWAY_CONTAINER=false
if docker container inspect "$GATEWAY_CONTAINER" >/dev/null 2>&1; then
  HAS_GATEWAY_CONTAINER=true
fi

mkdir -p "$ARTIFACT_DIR" "$METADATA_DIR" "$MOUNT_DIR"

log "writing inspect metadata into $METADATA_DIR"
docker inspect "$WEBSITE_CONTAINER" > "$METADATA_DIR/$WEBSITE_CONTAINER.inspect.json"
if [[ "$HAS_GATEWAY_CONTAINER" == "true" ]]; then
  docker inspect "$GATEWAY_CONTAINER" > "$METADATA_DIR/$GATEWAY_CONTAINER.inspect.json"
fi
docker network inspect "$NETWORK_NAME" > "$METADATA_DIR/$NETWORK_NAME.inspect.json"
docker ps -a --no-trunc > "$METADATA_DIR/docker-ps.txt"
docker images --digests > "$METADATA_DIR/docker-images.txt"
docker diff "$WEBSITE_CONTAINER" > "$METADATA_DIR/$WEBSITE_CONTAINER.diff.txt" || true
if [[ "$HAS_GATEWAY_CONTAINER" == "true" ]]; then
  docker diff "$GATEWAY_CONTAINER" > "$METADATA_DIR/$GATEWAY_CONTAINER.diff.txt" || true
fi
write_container_env_file "$WEBSITE_CONTAINER" "$METADATA_DIR/$WEBSITE_CONTAINER.env"
if [[ "$HAS_GATEWAY_CONTAINER" == "true" ]]; then
  write_container_env_file "$GATEWAY_CONTAINER" "$METADATA_DIR/$GATEWAY_CONTAINER.env"
fi

cat > "$METADATA_DIR/manifest.env" <<EOF
SNAPSHOT_CREATED_AT=$(date -Iseconds)
NETWORK_NAME=$NETWORK_NAME
NETWORK_SUBNET=$NETWORK_SUBNET
WEBSITE_CONTAINER=$WEBSITE_CONTAINER
GATEWAY_CONTAINER=$GATEWAY_CONTAINER
HAS_GATEWAY_CONTAINER=$HAS_GATEWAY_CONTAINER
WEBSITE_IMAGE_TAG=$WEBSITE_SNAPSHOT_IMAGE
GATEWAY_IMAGE_TAG=$GATEWAY_SNAPSHOT_IMAGE
YX_ROOT=$YX_ROOT
WEBSITE_MOUNT_DATA=$WEBSITE_MOUNT_DATA
WEBSITE_MOUNT_PAGES=$WEBSITE_MOUNT_PAGES
WEBSITE_MOUNT_CDN=$WEBSITE_MOUNT_CDN
MAIN_PORT=$MAIN_PORT
EOF

log "creating live container snapshot images without pausing traffic"
docker commit --pause=false "$WEBSITE_CONTAINER" "$WEBSITE_SNAPSHOT_IMAGE" >/dev/null
if [[ "$HAS_GATEWAY_CONTAINER" == "true" ]]; then
  docker commit --pause=false "$GATEWAY_CONTAINER" "$GATEWAY_SNAPSHOT_IMAGE" >/dev/null
fi

log "saving snapshot images"
docker save "$WEBSITE_SNAPSHOT_IMAGE" | gzip -1 > "$ARTIFACT_DIR/$WEBSITE_CONTAINER.image.tar.gz"
if [[ "$HAS_GATEWAY_CONTAINER" == "true" ]]; then
  docker save "$GATEWAY_SNAPSHOT_IMAGE" | gzip -1 > "$ARTIFACT_DIR/$GATEWAY_CONTAINER.image.tar.gz"
fi

log "archiving mounted directories"
tar_mount_dir "$WEBSITE_MOUNT_DATA" "$MOUNT_DIR/${WEBSITE_CONTAINER}.data.tar.gz"
tar_mount_dir "$WEBSITE_MOUNT_PAGES" "$MOUNT_DIR/${WEBSITE_CONTAINER}.pages.tar.gz"
tar_mount_dir "$WEBSITE_MOUNT_CDN" "$MOUNT_DIR/${WEBSITE_CONTAINER}.cdn_assets.tar.gz"

(
  cd "$SNAPSHOT_DIR"
  find . -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
)

log "snapshot ready: $SNAPSHOT_DIR"
printf '%s\n' "$SNAPSHOT_DIR"
