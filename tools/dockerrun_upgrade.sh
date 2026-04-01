#!/usr/bin/env bash
set -Eeuo pipefail

# One-click upgrade for docker-run deployment:
# 1) pull new images
# 2) sync latest /app/cdn_assets from website image to host (with --delete)
# 3) sync latest /app/update_logs from website image to host (merge)
# 4) recreate yx-website and yx-gateway containers
# 5) prune dangling old images

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing command: $1"
}

bool_true() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

# Defaults (can be overridden by environment variables)
YX_ROOT="${YX_ROOT:-/root/yxwebsite}"
NETWORK_NAME="${NETWORK_NAME:-yx-net}"
WEBSITE_CONTAINER="${WEBSITE_CONTAINER:-yx-website}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-yx-gateway}"
WEBSITE_IMAGE="${WEBSITE_IMAGE:-ghcr.io/zhizinan1997/yx_website:latest}"
GATEWAY_IMAGE="${GATEWAY_IMAGE:-ghcr.io/zhizinan1997/yx-gateway:latest}"
MAIN_PORT="${MAIN_PORT:-2026}"
CDN_PORT="${CDN_PORT:-2027}"
SKIP_PULL="${SKIP_PULL:-false}"
SYNC_PAGES="${SYNC_PAGES:-false}"
SYNC_UPDATE_LOGS="${SYNC_UPDATE_LOGS:-true}"
CLEAN_OLD_IMAGES="${CLEAN_OLD_IMAGES:-true}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'USAGE'
Usage:
  bash tools/dockerrun_upgrade.sh

Optional environment variables:
  YX_ROOT=/root/yxwebsite
  NETWORK_NAME=yx-net
  WEBSITE_CONTAINER=yx-website
  GATEWAY_CONTAINER=yx-gateway
  WEBSITE_IMAGE=ghcr.io/zhizinan1997/yx_website:latest
  GATEWAY_IMAGE=ghcr.io/zhizinan1997/yx-gateway:latest
  MAIN_PORT=2026
  CDN_PORT=2027
  SKIP_PULL=false
  SYNC_PAGES=false
  SYNC_UPDATE_LOGS=true
  CLEAN_OLD_IMAGES=true

Runtime envs for website container (auto-reuse from old container if present):
  APP_ENV, SECRET_KEY, PUBLIC_BASE_URL, TRUST_PROXY_HEADERS, SESSION_COOKIE_SECURE,
  ADMIN_USERNAME, ADMIN_PASSWORD_HASH, ADMIN_PASSWORD,
  CDN_ENABLED, CDN_DOMAIN, TURNSTILE_ENABLED, TURNSTILE_SITE_KEY, TURNSTILE_SECRET_KEY
USAGE
  exit 0
fi

require_cmd docker
require_cmd rsync

if [[ -z "$YX_ROOT" || "$YX_ROOT" == "/" ]]; then
  die "YX_ROOT is invalid: '$YX_ROOT'"
fi

DATA_DIR="$YX_ROOT/data"
PAGES_DIR="$YX_ROOT/pages"
CDN_DIR="$YX_ROOT/cdn_assets"
UPDATE_LOGS_DIR="$YX_ROOT/update_logs"
TMP_CDN_DIR="$YX_ROOT/.tmp-cdn-assets"
TMP_PAGES_DIR="$YX_ROOT/.tmp-pages"
TMP_UPDATE_LOGS_DIR="$YX_ROOT/.tmp-update-logs"
TMP_CONTAINER="${TMP_CONTAINER:-yx-website-assets-sync-$(date +%s)-$$}"

EXISTING_ENV_LINES=""
if docker container inspect "$WEBSITE_CONTAINER" >/dev/null 2>&1; then
  EXISTING_ENV_LINES="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$WEBSITE_CONTAINER" || true)"
fi

get_existing_env() {
  local key="$1"
  if [[ -z "$EXISTING_ENV_LINES" ]]; then
    return 0
  fi
  awk -F= -v k="$key" '$1==k { $1=""; sub(/^=/, ""); print; exit }' <<< "$EXISTING_ENV_LINES"
}

resolve_env() {
  local key="$1"
  local default_value="$2"
  local required_flag="$3"
  local value="${!key-}"

  if [[ -z "$value" ]]; then
    value="$(get_existing_env "$key")"
  fi
  if [[ -z "$value" ]]; then
    value="$default_value"
  fi
  if [[ "$required_flag" == "required" && -z "$value" ]]; then
    die "missing required env '$key'. Set it before running the script."
  fi

  printf '%s' "$value"
}

APP_ENV_VAL="$(resolve_env APP_ENV production optional)"
SECRET_KEY_VAL="$(resolve_env SECRET_KEY "" required)"
PUBLIC_BASE_URL_VAL="$(resolve_env PUBLIC_BASE_URL "" required)"
TRUST_PROXY_HEADERS_VAL="$(resolve_env TRUST_PROXY_HEADERS true optional)"
SESSION_COOKIE_SECURE_VAL="$(resolve_env SESSION_COOKIE_SECURE true optional)"
ADMIN_USERNAME_VAL="$(resolve_env ADMIN_USERNAME admin optional)"
ADMIN_PASSWORD_HASH_VAL="$(resolve_env ADMIN_PASSWORD_HASH "" optional)"
ADMIN_PASSWORD_VAL="$(resolve_env ADMIN_PASSWORD "" optional)"
CDN_ENABLED_VAL="$(resolve_env CDN_ENABLED false optional)"
CDN_DOMAIN_VAL="$(resolve_env CDN_DOMAIN "" optional)"
TURNSTILE_ENABLED_VAL="$(resolve_env TURNSTILE_ENABLED false optional)"
TURNSTILE_SITE_KEY_VAL="$(resolve_env TURNSTILE_SITE_KEY "" optional)"
TURNSTILE_SECRET_KEY_VAL="$(resolve_env TURNSTILE_SECRET_KEY "" optional)"

if [[ -z "$ADMIN_PASSWORD_HASH_VAL" && -z "$ADMIN_PASSWORD_VAL" && ! -s "$DATA_DIR/admin_users.json" ]]; then
  die "ADMIN_PASSWORD_HASH/ADMIN_PASSWORD not found and $DATA_DIR/admin_users.json is missing."
fi

cleanup() {
  docker rm -f "$TMP_CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$TMP_CDN_DIR" "$TMP_PAGES_DIR" "$TMP_UPDATE_LOGS_DIR"
}
trap cleanup EXIT

log "prepare directories and network"
mkdir -p "$DATA_DIR" "$PAGES_DIR" "$CDN_DIR" "$UPDATE_LOGS_DIR"
docker network create "$NETWORK_NAME" >/dev/null 2>&1 || true

if ! bool_true "$SKIP_PULL"; then
  log "pull latest images"
  docker pull "$WEBSITE_IMAGE"
  docker pull "$GATEWAY_IMAGE"
else
  log "skip image pull (SKIP_PULL=$SKIP_PULL)"
fi

log "export latest cdn_assets from website image"
docker create --name "$TMP_CONTAINER" "$WEBSITE_IMAGE" >/dev/null
rm -rf "$TMP_CDN_DIR"
mkdir -p "$TMP_CDN_DIR"
docker cp "$TMP_CONTAINER:/app/cdn_assets/." "$TMP_CDN_DIR/"

log "sync cdn_assets to host (rsync --delete)"
rsync -a --delete "$TMP_CDN_DIR/" "$CDN_DIR/"

if bool_true "$SYNC_PAGES"; then
  log "SYNC_PAGES enabled: merge pages from image into host pages directory"
  rm -rf "$TMP_PAGES_DIR"
  mkdir -p "$TMP_PAGES_DIR"
  docker cp "$TMP_CONTAINER:/app/pages/." "$TMP_PAGES_DIR/"
  rsync -a "$TMP_PAGES_DIR/" "$PAGES_DIR/"
fi

if bool_true "$SYNC_UPDATE_LOGS"; then
  log "SYNC_UPDATE_LOGS enabled: merge update_logs from image into host update_logs directory"
  rm -rf "$TMP_UPDATE_LOGS_DIR"
  mkdir -p "$TMP_UPDATE_LOGS_DIR"
  if docker cp "$TMP_CONTAINER:/app/update_logs/." "$TMP_UPDATE_LOGS_DIR/" >/dev/null 2>&1; then
    rsync -a "$TMP_UPDATE_LOGS_DIR/" "$UPDATE_LOGS_DIR/"
  else
    log "WARN: no /app/update_logs found in image, skip update_logs sync"
  fi
fi

log "recreate containers"
docker rm -f "$GATEWAY_CONTAINER" "$WEBSITE_CONTAINER" >/dev/null 2>&1 || true

website_cmd=(
  docker run -d
  --name "$WEBSITE_CONTAINER"
  --restart unless-stopped
  --network "$NETWORK_NAME"
  --network-alias "$WEBSITE_CONTAINER"
  -e "APP_ENV=$APP_ENV_VAL"
  -e "SECRET_KEY=$SECRET_KEY_VAL"
  -e "PUBLIC_BASE_URL=$PUBLIC_BASE_URL_VAL"
  -e "TRUST_PROXY_HEADERS=$TRUST_PROXY_HEADERS_VAL"
  -e "SESSION_COOKIE_SECURE=$SESSION_COOKIE_SECURE_VAL"
  -e "ADMIN_USERNAME=$ADMIN_USERNAME_VAL"
  -e "CDN_ENABLED=$CDN_ENABLED_VAL"
  -e "TURNSTILE_ENABLED=$TURNSTILE_ENABLED_VAL"
  -v "$DATA_DIR:/app/data"
  -v "$PAGES_DIR:/app/pages"
  -v "$CDN_DIR:/app/cdn_assets"
  -v "$UPDATE_LOGS_DIR:/app/update_logs"
)

if [[ -n "$ADMIN_PASSWORD_HASH_VAL" ]]; then
  website_cmd+=( -e "ADMIN_PASSWORD_HASH=$ADMIN_PASSWORD_HASH_VAL" )
fi
if [[ -n "$ADMIN_PASSWORD_VAL" ]]; then
  website_cmd+=( -e "ADMIN_PASSWORD=$ADMIN_PASSWORD_VAL" )
fi
if [[ -n "$CDN_DOMAIN_VAL" ]]; then
  website_cmd+=( -e "CDN_DOMAIN=$CDN_DOMAIN_VAL" )
fi
if [[ -n "$TURNSTILE_SITE_KEY_VAL" ]]; then
  website_cmd+=( -e "TURNSTILE_SITE_KEY=$TURNSTILE_SITE_KEY_VAL" )
fi
if [[ -n "$TURNSTILE_SECRET_KEY_VAL" ]]; then
  website_cmd+=( -e "TURNSTILE_SECRET_KEY=$TURNSTILE_SECRET_KEY_VAL" )
fi

website_cmd+=( "$WEBSITE_IMAGE" )
"${website_cmd[@]}" >/dev/null

gateway_cmd=(
  docker run -d
  --name "$GATEWAY_CONTAINER"
  --restart unless-stopped
  --network "$NETWORK_NAME"
  -p "127.0.0.1:${MAIN_PORT}:80"
  -p "127.0.0.1:${CDN_PORT}:81"
  -v "$CDN_DIR:/app/cdn_assets:ro"
  "$GATEWAY_IMAGE"
)
"${gateway_cmd[@]}" >/dev/null

log "verify containers"
for c in "$WEBSITE_CONTAINER" "$GATEWAY_CONTAINER"; do
  if ! docker ps --filter "name=^/${c}$" --format '{{.Names}}' | grep -qx "$c"; then
    die "container '$c' is not running"
  fi
done

if bool_true "$CLEAN_OLD_IMAGES"; then
  log "prune dangling old images"
  docker image prune -f >/dev/null || log "WARN: docker image prune failed"
fi

log "upgrade completed"
log "main site: http://127.0.0.1:${MAIN_PORT}"
log "cdn site : http://127.0.0.1:${CDN_PORT}"
