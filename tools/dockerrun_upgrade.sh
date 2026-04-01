#!/usr/bin/env bash
set -Eeuo pipefail

# One-click upgrade for docker-run deployment:
# 1) pull new images
# 2) smart-sync /app/pages from image into host bind mount
# 3) recreate yx-website and yx-gateway containers
# 4) prune dangling old images

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

phase() {
  printf '\n'
  log "==> $*"
}

info() {
  log "    $*"
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

normalize_sync_pages_mode() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON|smart|SMART|merge|MERGE)
      printf 'smart'
      ;;
    add|ADD|additive|ADDITIVE|missing-only|MISSING-ONLY)
      printf 'additive'
      ;;
    0|false|FALSE|no|NO|off|OFF|skip|SKIP|'')
      printf 'skip'
      ;;
    *)
      die "unsupported SYNC_PAGES value: '${1:-}' (allowed: smart|additive|false)"
      ;;
  esac
}

has_regular_files() {
  local dir="$1"
  [[ -d "$dir" ]] || return 1
  find "$dir" -type f -print -quit 2>/dev/null | grep -q .
}

count_regular_files() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    printf '0'
    return 0
  fi
  find "$dir" -type f 2>/dev/null | wc -l | tr -d ' '
}

copy_with_parents() {
  local src="$1"
  local dst="$2"
  mkdir -p "$(dirname "$dst")"
  cp -f "$src" "$dst"
}

save_conflict_copy() {
  local src="$1"
  local rel="$2"
  local conflicts_dir="$3"
  local dst="$conflicts_dir/$rel"
  mkdir -p "$(dirname "$dst")"
  cp -f "$src" "$dst"
}

export_image_tree() {
  local image_ref="$1"
  local container_name="$2"
  local source_path="$3"
  local target_dir="$4"

  docker create --name "$container_name" "$image_ref" >/dev/null
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  docker cp "$container_name:${source_path}/." "$target_dir/" >/dev/null 2>&1
}

smart_merge_pages() {
  local base_dir="$1"
  local new_dir="$2"
  local host_dir="$3"
  local conflicts_dir="$4"
  local added=0
  local updated=0
  local kept_local=0
  local identical=0
  local conflicts=0
  local upstream_removed=0

  rm -rf "$conflicts_dir"
  mkdir -p "$conflicts_dir"

  while IFS= read -r -d '' new_file; do
    local rel="${new_file#$new_dir/}"
    local host_file="$host_dir/$rel"
    local base_file="$base_dir/$rel"

    if [[ ! -e "$host_file" ]]; then
      copy_with_parents "$new_file" "$host_file"
      added=$((added + 1))
      continue
    fi

    if [[ ! -e "$base_file" ]]; then
      if cmp -s "$host_file" "$new_file"; then
        identical=$((identical + 1))
      else
        save_conflict_copy "$new_file" "$rel" "$conflicts_dir"
        conflicts=$((conflicts + 1))
        kept_local=$((kept_local + 1))
      fi
      continue
    fi

    if cmp -s "$host_file" "$base_file"; then
      if cmp -s "$base_file" "$new_file"; then
        identical=$((identical + 1))
      else
        copy_with_parents "$new_file" "$host_file"
        updated=$((updated + 1))
      fi
      continue
    fi

    if cmp -s "$base_file" "$new_file" || cmp -s "$host_file" "$new_file"; then
      kept_local=$((kept_local + 1))
      continue
    fi

    save_conflict_copy "$new_file" "$rel" "$conflicts_dir"
    conflicts=$((conflicts + 1))
    kept_local=$((kept_local + 1))
  done < <(find "$new_dir" -type f -print0)

  while IFS= read -r -d '' base_file; do
    local rel="${base_file#$base_dir/}"
    local new_file="$new_dir/$rel"
    local host_file="$host_dir/$rel"

    [[ -e "$new_file" ]] && continue
    [[ -e "$host_file" ]] || continue

    if cmp -s "$host_file" "$base_file"; then
      upstream_removed=$((upstream_removed + 1))
    fi
  done < <(find "$base_dir" -type f -print0)

  log "pages sync summary: added=$added updated=$updated kept_local=$kept_local identical=$identical conflicts=$conflicts upstream_removed_kept=$upstream_removed"
  if (( conflicts > 0 )); then
    log "WARN: conflicting new image pages were saved to $conflicts_dir"
  fi
  if (( upstream_removed > 0 )); then
    log "WARN: some pages were removed from the new image but kept on host because local bind mount owns final data"
  fi
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
SYNC_PAGES="${SYNC_PAGES:-smart}"
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
  SYNC_PAGES=smart
  CLEAN_OLD_IMAGES=true

SYNC_PAGES modes:
  smart      3-way merge using previous image pages as merge base (recommended)
  additive   only add files missing on host, never update existing host files
  false      skip pages sync entirely

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

SYNC_PAGES_MODE="$(normalize_sync_pages_mode "$SYNC_PAGES")"

DATA_DIR="$YX_ROOT/data"
PAGES_DIR="$YX_ROOT/pages"
PAGES_BASELINE_DIR="${PAGES_BASELINE_DIR:-$YX_ROOT/.pages-image-baseline}"
PAGES_CONFLICTS_DIR="${PAGES_CONFLICTS_DIR:-$YX_ROOT/.pages-merge-conflicts}"
TMP_PAGES_DIR="$YX_ROOT/.tmp-pages"
TMP_OLD_PAGES_DIR="$YX_ROOT/.tmp-pages-old"
TMP_NEW_CONTAINER="${TMP_NEW_CONTAINER:-yx-website-pages-new-$(date +%s)-$$}"
TMP_OLD_CONTAINER="${TMP_OLD_CONTAINER:-yx-website-pages-old-$(date +%s)-$$}"

EXISTING_ENV_LINES=""
EXISTING_IMAGE_REF=""
if docker container inspect "$WEBSITE_CONTAINER" >/dev/null 2>&1; then
  EXISTING_ENV_LINES="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$WEBSITE_CONTAINER" || true)"
  EXISTING_IMAGE_REF="$(docker inspect -f '{{.Image}}' "$WEBSITE_CONTAINER" || true)"
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
  docker rm -f "$TMP_NEW_CONTAINER" "$TMP_OLD_CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$TMP_PAGES_DIR" "$TMP_OLD_PAGES_DIR"
}
trap cleanup EXIT

phase "Upgrade started"
info "YX_ROOT=$YX_ROOT"
info "NETWORK_NAME=$NETWORK_NAME"
info "SYNC_PAGES_MODE=$SYNC_PAGES_MODE"
info "WEBSITE_IMAGE=$WEBSITE_IMAGE"
info "GATEWAY_IMAGE=$GATEWAY_IMAGE"
if [[ -n "$EXISTING_IMAGE_REF" ]]; then
  info "existing website image ref: $EXISTING_IMAGE_REF"
else
  info "existing website image ref: <none>"
fi

phase "Prepare directories and network"
mkdir -p "$DATA_DIR" "$PAGES_DIR"
docker network create "$NETWORK_NAME" >/dev/null 2>&1 || true
info "data dir ready: $DATA_DIR"
info "pages dir ready: $PAGES_DIR"

if ! bool_true "$SKIP_PULL"; then
  phase "Pull latest images"
  info "pulling website image"
  docker pull "$WEBSITE_IMAGE"
  info "pulling gateway image"
  docker pull "$GATEWAY_IMAGE"
else
  phase "Skip image pull"
  info "SKIP_PULL=$SKIP_PULL"
fi

if [[ "$SYNC_PAGES_MODE" != "skip" ]]; then
  phase "Sync pages from website image"
  info "export latest pages from new website image"
  export_image_tree "$WEBSITE_IMAGE" "$TMP_NEW_CONTAINER" "/app/pages" "$TMP_PAGES_DIR" || die "failed to export /app/pages from $WEBSITE_IMAGE"
  info "new image pages exported: $(count_regular_files "$TMP_PAGES_DIR") files"

  BASE_PAGES_SOURCE=""
  BASE_PAGES_LABEL=""
  if [[ -n "$EXISTING_IMAGE_REF" ]]; then
    info "export previous image pages as merge base"
    if export_image_tree "$EXISTING_IMAGE_REF" "$TMP_OLD_CONTAINER" "/app/pages" "$TMP_OLD_PAGES_DIR"; then
      BASE_PAGES_SOURCE="$TMP_OLD_PAGES_DIR"
      BASE_PAGES_LABEL="previous-image"
      info "merge base exported from previous image: $(count_regular_files "$TMP_OLD_PAGES_DIR") files"
    else
      log "WARN: failed to export previous image pages from $EXISTING_IMAGE_REF"
    fi
  fi

  if [[ -z "$BASE_PAGES_SOURCE" ]] && has_regular_files "$PAGES_BASELINE_DIR"; then
    info "use stored pages baseline from $PAGES_BASELINE_DIR"
    BASE_PAGES_SOURCE="$PAGES_BASELINE_DIR"
    BASE_PAGES_LABEL="stored-baseline"
    info "stored baseline files: $(count_regular_files "$PAGES_BASELINE_DIR")"
  fi

  if [[ "$SYNC_PAGES_MODE" == "additive" ]]; then
    info "SYNC_PAGES=additive: only copy files missing on host"
    rsync -a --ignore-existing "$TMP_PAGES_DIR/" "$PAGES_DIR/"
  elif [[ -n "$BASE_PAGES_SOURCE" ]]; then
    info "SYNC_PAGES=smart: 3-way merge pages into host bind mount"
    info "merge base source: $BASE_PAGES_LABEL"
    smart_merge_pages "$BASE_PAGES_SOURCE" "$TMP_PAGES_DIR" "$PAGES_DIR" "$PAGES_CONFLICTS_DIR"
  else
    log "WARN: no merge base available; fallback to additive pages sync for this run"
    rsync -a --ignore-existing "$TMP_PAGES_DIR/" "$PAGES_DIR/"
  fi

  info "refresh stored pages baseline"
  rm -rf "$PAGES_BASELINE_DIR"
  mkdir -p "$PAGES_BASELINE_DIR"
  rsync -a --delete "$TMP_PAGES_DIR/" "$PAGES_BASELINE_DIR/"
  info "stored baseline refreshed: $(count_regular_files "$PAGES_BASELINE_DIR") files"
  if has_regular_files "$PAGES_CONFLICTS_DIR"; then
    log "WARN: page merge conflicts saved under $PAGES_CONFLICTS_DIR"
  else
    info "no page merge conflicts detected"
  fi
else
  phase "Skip pages sync"
  info "SYNC_PAGES_MODE=skip"
fi

phase "Recreate containers"
info "remove old containers if present"
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
info "start website container"
WEBSITE_CONTAINER_ID="$("${website_cmd[@]}")"
info "website container id: ${WEBSITE_CONTAINER_ID:0:12}"

gateway_cmd=(
  docker run -d
  --name "$GATEWAY_CONTAINER"
  --restart unless-stopped
  --network "$NETWORK_NAME"
  -p "127.0.0.1:${MAIN_PORT}:80"
  -p "127.0.0.1:${CDN_PORT}:81"
  "$GATEWAY_IMAGE"
)
info "start gateway container"
GATEWAY_CONTAINER_ID="$("${gateway_cmd[@]}")"
info "gateway container id: ${GATEWAY_CONTAINER_ID:0:12}"

phase "Verify containers"
for c in "$WEBSITE_CONTAINER" "$GATEWAY_CONTAINER"; do
  if ! docker ps --filter "name=^/${c}$" --format '{{.Names}}' | grep -qx "$c"; then
    die "container '$c' is not running"
  fi
  info "container running: $c"
done

if bool_true "$CLEAN_OLD_IMAGES"; then
  phase "Prune dangling old images"
  docker image prune -f >/dev/null || log "WARN: docker image prune failed"
  info "dangling images pruned"
else
  phase "Skip dangling image prune"
  info "CLEAN_OLD_IMAGES=$CLEAN_OLD_IMAGES"
fi

phase "Upgrade completed"
info "main site: http://127.0.0.1:${MAIN_PORT}"
info "cdn site : http://127.0.0.1:${CDN_PORT}"
