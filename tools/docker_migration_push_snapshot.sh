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

require_cmd sshpass
require_cmd ssh
require_cmd rsync

SNAPSHOT_DIR="${1:-}"
DEST_HOST="${2:-}"
DEST_PASSWORD="${3:-}"
DEST_USER="${DEST_USER:-root}"
DEST_ROOT="${DEST_ROOT:-/root/yx-migration-import}"

[[ -n "$SNAPSHOT_DIR" ]] || die "usage: $0 SNAPSHOT_DIR DEST_HOST DEST_PASSWORD"
[[ -d "$SNAPSHOT_DIR" ]] || die "snapshot directory not found: $SNAPSHOT_DIR"
[[ -n "$DEST_HOST" ]] || die "missing destination host"
[[ -n "$DEST_PASSWORD" ]] || die "missing destination password"

SNAPSHOT_BASENAME="$(basename "$SNAPSHOT_DIR")"
DEST_DIR="$DEST_ROOT/$SNAPSHOT_BASENAME"

log "preparing destination directory: $DEST_USER@$DEST_HOST:$DEST_DIR"
sshpass -p "$DEST_PASSWORD" ssh \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  "$DEST_USER@$DEST_HOST" \
  "rm -rf '$DEST_DIR' && mkdir -p '$DEST_DIR'"

log "transferring snapshot: $SNAPSHOT_DIR -> $DEST_USER@$DEST_HOST:$DEST_DIR"
sshpass -p "$DEST_PASSWORD" rsync -a --info=progress2 \
  -e "ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
  "$SNAPSHOT_DIR/" "$DEST_USER@$DEST_HOST:$DEST_DIR/"

log "snapshot transfer completed"
