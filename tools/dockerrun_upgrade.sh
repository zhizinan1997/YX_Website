#!/usr/bin/env bash
set -Eeuo pipefail

# One-click upgrade for docker-run deployment:
# 1) pull new images
# 2) smart-sync /app/pages and /app/data from image into host bind mounts
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
  log "错误：$*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令：$1"
}

bool_true() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

normalize_sync_mode() {
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
      die "不支持的同步模式：'${1:-}'（可选：smart|additive|false）"
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

count_all_entries() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    printf '0'
    return 0
  fi
  find "$dir" -mindepth 1 2>/dev/null | wc -l | tr -d ' '
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

log_file_action() {
  local label="$1"
  local action="$2"
  local rel="$3"
  local extra="${4:-}"

  if [[ -n "$extra" ]]; then
    info "[$label] $action：$rel -> $extra"
  else
    info "[$label] $action：$rel"
  fi
}

log_tree_state() {
  local label="$1"
  local dir="$2"
  info "[$label] 目录：$dir"
  info "[$label] 文件数：$(count_regular_files "$dir")，总条目数：$(count_all_entries "$dir")"
}

remove_container_if_exists() {
  local name="$1"

  if docker container inspect "$name" >/dev/null 2>&1; then
    info "检测到已有容器：$name，正在删除"
    docker rm -f "$name" >/dev/null
    info "旧容器已删除：$name"
  else
    info "未发现旧容器：$name"
  fi
}

export_image_tree() {
  local image_ref="$1"
  local container_name="$2"
  local source_path="$3"
  local target_dir="$4"
  local status=0

  info "准备创建临时导出容器：$container_name"
  docker rm -f "$container_name" >/dev/null 2>&1 || true
  docker create --name "$container_name" "$image_ref" >/dev/null
  info "临时导出容器已创建：$container_name"
  info "清理旧的临时目录：$target_dir"
  rm -rf "$target_dir"
  mkdir -p "$target_dir"
  info "开始从容器复制目录：$source_path -> $target_dir"
  if docker cp "$container_name:${source_path}/." "$target_dir/" >/dev/null 2>&1; then
    info "目录复制完成：$source_path -> $target_dir"
  else
    status=$?
    info "目录复制失败，docker cp 返回码：$status"
  fi
  info "清理临时导出容器：$container_name"
  docker rm -f "$container_name" >/dev/null 2>&1 || true
  return "$status"
}

smart_merge_tree() {
  local label="$1"
  local base_dir="$2"
  local new_dir="$3"
  local host_dir="$4"
  local conflicts_dir="$5"
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
      log_file_action "$label" "新增文件" "$rel"
      continue
    fi

    if [[ ! -e "$base_file" ]]; then
      if cmp -s "$host_file" "$new_file"; then
        identical=$((identical + 1))
        log_file_action "$label" "宿主机已有同内容文件，无需处理" "$rel"
      else
        save_conflict_copy "$new_file" "$rel" "$conflicts_dir"
        conflicts=$((conflicts + 1))
        kept_local=$((kept_local + 1))
        log_file_action "$label" "发现冲突，保留宿主机版本" "$rel" "$conflicts_dir/$rel"
      fi
      continue
    fi

    if cmp -s "$host_file" "$base_file"; then
      if cmp -s "$base_file" "$new_file"; then
        identical=$((identical + 1))
        log_file_action "$label" "新旧镜像与宿主机一致，无需处理" "$rel"
      else
        copy_with_parents "$new_file" "$host_file"
        updated=$((updated + 1))
        log_file_action "$label" "更新文件" "$rel"
      fi
      continue
    fi

    if cmp -s "$base_file" "$new_file"; then
      kept_local=$((kept_local + 1))
      log_file_action "$label" "宿主机已修改，保留本地版本" "$rel"
      continue
    fi

    if cmp -s "$host_file" "$new_file"; then
      kept_local=$((kept_local + 1))
      log_file_action "$label" "宿主机文件已是最新版本，无需替换" "$rel"
      continue
    fi

    save_conflict_copy "$new_file" "$rel" "$conflicts_dir"
    conflicts=$((conflicts + 1))
    kept_local=$((kept_local + 1))
    log_file_action "$label" "发现冲突，保留宿主机版本" "$rel" "$conflicts_dir/$rel"
  done < <(find "$new_dir" -type f -print0)

  while IFS= read -r -d '' base_file; do
    local rel="${base_file#$base_dir/}"
    local new_file="$new_dir/$rel"
    local host_file="$host_dir/$rel"

    [[ -e "$new_file" ]] && continue
    [[ -e "$host_file" ]] || continue

    if cmp -s "$host_file" "$base_file"; then
      upstream_removed=$((upstream_removed + 1))
      log_file_action "$label" "新镜像已删除该文件，但宿主机继续保留" "$rel"
    fi
  done < <(find "$base_dir" -type f -print0)

  log "$label 同步结果：新增 $added 个，更新 $updated 个，保留本地 $kept_local 个，相同 $identical 个，冲突 $conflicts 个，上游已删除但本地保留 $upstream_removed 个"
  if (( conflicts > 0 )); then
    log "警告：$label 存在冲突，新镜像版本已保存到 $conflicts_dir"
  fi
  if (( upstream_removed > 0 )); then
    log "警告：新镜像里有部分 $label 文件已删除，但由于宿主机挂载目录为最终数据来源，这些文件仍保留在本地"
  fi
}

additive_sync_tree() {
  local label="$1"
  local new_dir="$2"
  local host_dir="$3"
  local added=0
  local skipped=0

  while IFS= read -r -d '' new_file; do
    local rel="${new_file#$new_dir/}"
    local host_file="$host_dir/$rel"

    if [[ ! -e "$host_file" ]]; then
      copy_with_parents "$new_file" "$host_file"
      added=$((added + 1))
      log_file_action "$label" "新增文件" "$rel"
    else
      skipped=$((skipped + 1))
      log_file_action "$label" "宿主机已存在该文件，按 additive 模式跳过" "$rel"
    fi
  done < <(find "$new_dir" -type f -print0)

  log "$label 补充模式结果：新增 $added 个，宿主机已存在并跳过 $skipped 个"
}

sync_image_tree() {
  local label="$1"
  local source_path="$2"
  local host_dir="$3"
  local baseline_dir="$4"
  local conflicts_dir="$5"
  local tmp_new_dir="$6"
  local tmp_old_dir="$7"
  local sync_mode="$8"

  phase "开始同步${label}"
  log_tree_state "${label}宿主机当前状态" "$host_dir"
  info "正在从新镜像导出${label}：$WEBSITE_IMAGE -> $source_path"
  export_image_tree "$WEBSITE_IMAGE" "$TMP_NEW_CONTAINER" "$source_path" "$tmp_new_dir" || die "无法从镜像 $WEBSITE_IMAGE 导出 $source_path"
  info "新镜像中的${label}已导出，共 $(count_regular_files "$tmp_new_dir") 个文件"
  log_tree_state "${label}新镜像导出结果" "$tmp_new_dir"

  local base_source=""
  local base_label=""
  if [[ -n "$EXISTING_IMAGE_REF" ]]; then
    info "正在导出上一版镜像中的${label}，作为三方合并基线"
    if export_image_tree "$EXISTING_IMAGE_REF" "$TMP_OLD_CONTAINER" "$source_path" "$tmp_old_dir"; then
      base_source="$tmp_old_dir"
      base_label="上一版镜像"
      info "已成功导出上一版镜像基线，共 $(count_regular_files "$tmp_old_dir") 个文件"
      log_tree_state "${label}上一版镜像基线" "$tmp_old_dir"
    else
      log "警告：无法从上一版镜像 $EXISTING_IMAGE_REF 导出${label}，将尝试使用本地基线"
    fi
  fi

  if [[ -z "$base_source" ]] && has_regular_files "$baseline_dir"; then
    info "正在使用本地保存的${label}基线：$baseline_dir"
    base_source="$baseline_dir"
    base_label="本地保存基线"
    info "本地基线包含 $(count_regular_files "$baseline_dir") 个文件"
    log_tree_state "${label}本地保存基线" "$baseline_dir"
  fi

  if [[ "$sync_mode" == "additive" ]]; then
    info "当前为 additive 模式：仅补充宿主机缺失的${label}文件，不覆盖已有文件"
    additive_sync_tree "$label" "$tmp_new_dir" "$host_dir"
  elif [[ -n "$base_source" ]]; then
    info "当前为 smart 模式：将对${label}执行三方合并"
    info "本次使用的合并基线来源：$base_label"
    smart_merge_tree "$label" "$base_source" "$tmp_new_dir" "$host_dir" "$conflicts_dir"
  else
    log "警告：当前没有可用合并基线，本次${label}同步将退回为 additive 模式"
    additive_sync_tree "$label" "$tmp_new_dir" "$host_dir"
  fi

  info "正在刷新本地保存的${label}基线"
  rm -rf "$baseline_dir"
  mkdir -p "$baseline_dir"
  rsync -a --delete "$tmp_new_dir/" "$baseline_dir/"
  info "本地${label}基线已刷新，共 $(count_regular_files "$baseline_dir") 个文件"
  log_tree_state "${label}刷新后的本地基线" "$baseline_dir"
  if has_regular_files "$conflicts_dir"; then
    log "警告：${label}合并冲突文件已保存到 $conflicts_dir"
    log_tree_state "${label}冲突文件目录" "$conflicts_dir"
  else
    info "${label}未发现合并冲突"
  fi
  log_tree_state "${label}同步后的宿主机状态" "$host_dir"
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
SYNC_DATA="${SYNC_DATA:-smart}"
CLEAN_OLD_IMAGES="${CLEAN_OLD_IMAGES:-true}"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'USAGE'
用法：
  bash tools/dockerrun_upgrade.sh

可选环境变量：
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
  SYNC_DATA=smart
  CLEAN_OLD_IMAGES=true

SYNC_PAGES / SYNC_DATA 模式说明：
  smart      使用上一版镜像树作为基线进行三方合并（推荐）
  additive   只补充宿主机缺失的文件，绝不覆盖已有文件
  false      跳过同步

网站容器运行时环境变量（如旧容器存在，会自动复用）：
  APP_ENV, SECRET_KEY, PUBLIC_BASE_URL, TRUST_PROXY_HEADERS, SESSION_COOKIE_SECURE,
  ADMIN_USERNAME,
  CDN_ENABLED, CDN_DOMAIN, TURNSTILE_ENABLED, TURNSTILE_SITE_KEY, TURNSTILE_SECRET_KEY

仅首次初始化管理员时需要的环境变量（admin_users.json 不存在时才需要）：
  ADMIN_PASSWORD_HASH, ADMIN_PASSWORD
USAGE
  exit 0
fi

require_cmd docker
require_cmd rsync

if [[ -z "$YX_ROOT" || "$YX_ROOT" == "/" ]]; then
  die "YX_ROOT 无效：'$YX_ROOT'"
fi

SYNC_PAGES_MODE="$(normalize_sync_mode "$SYNC_PAGES")"
SYNC_DATA_MODE="$(normalize_sync_mode "$SYNC_DATA")"

DATA_DIR="$YX_ROOT/data"
PAGES_DIR="$YX_ROOT/pages"
DATA_BASELINE_DIR="${DATA_BASELINE_DIR:-$YX_ROOT/.data-image-baseline}"
DATA_CONFLICTS_DIR="${DATA_CONFLICTS_DIR:-$YX_ROOT/.data-merge-conflicts}"
PAGES_BASELINE_DIR="${PAGES_BASELINE_DIR:-$YX_ROOT/.pages-image-baseline}"
PAGES_CONFLICTS_DIR="${PAGES_CONFLICTS_DIR:-$YX_ROOT/.pages-merge-conflicts}"
TMP_DATA_DIR="$YX_ROOT/.tmp-data"
TMP_OLD_DATA_DIR="$YX_ROOT/.tmp-data-old"
TMP_PAGES_DIR="$YX_ROOT/.tmp-pages"
TMP_OLD_PAGES_DIR="$YX_ROOT/.tmp-pages-old"
TMP_NEW_CONTAINER="${TMP_NEW_CONTAINER:-yx-website-export-new-$(date +%s)-$$}"
TMP_OLD_CONTAINER="${TMP_OLD_CONTAINER:-yx-website-export-old-$(date +%s)-$$}"

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
    die "缺少必填环境变量 '$key'，请先设置后再运行脚本。"
  fi

  printf '%s' "$value"
}

APP_ENV_VAL="$(resolve_env APP_ENV production optional)"
SECRET_KEY_VAL="$(resolve_env SECRET_KEY "" required)"
PUBLIC_BASE_URL_VAL="$(resolve_env PUBLIC_BASE_URL "" required)"
TRUST_PROXY_HEADERS_VAL="$(resolve_env TRUST_PROXY_HEADERS true optional)"
SESSION_COOKIE_SECURE_VAL="$(resolve_env SESSION_COOKIE_SECURE true optional)"
ADMIN_USERNAME_VAL="$(resolve_env ADMIN_USERNAME admin optional)"
CDN_ENABLED_VAL="$(resolve_env CDN_ENABLED false optional)"
CDN_DOMAIN_VAL="$(resolve_env CDN_DOMAIN "" optional)"
TURNSTILE_ENABLED_VAL="$(resolve_env TURNSTILE_ENABLED false optional)"
TURNSTILE_SITE_KEY_VAL="$(resolve_env TURNSTILE_SITE_KEY "" optional)"
TURNSTILE_SECRET_KEY_VAL="$(resolve_env TURNSTILE_SECRET_KEY "" optional)"

HAS_BOOTSTRAPPED_ADMIN=false
if [[ -s "$DATA_DIR/admin_users.json" ]]; then
  HAS_BOOTSTRAPPED_ADMIN=true
fi

if [[ "$HAS_BOOTSTRAPPED_ADMIN" == "true" ]]; then
  ADMIN_PASSWORD_HASH_VAL="${ADMIN_PASSWORD_HASH-}"
  ADMIN_PASSWORD_VAL="${ADMIN_PASSWORD-}"
else
  ADMIN_PASSWORD_HASH_VAL="$(resolve_env ADMIN_PASSWORD_HASH "" optional)"
  ADMIN_PASSWORD_VAL="$(resolve_env ADMIN_PASSWORD "" optional)"
fi

if [[ -z "$ADMIN_PASSWORD_HASH_VAL" && -z "$ADMIN_PASSWORD_VAL" && "$HAS_BOOTSTRAPPED_ADMIN" != "true" ]]; then
  die "未提供 ADMIN_PASSWORD_HASH 或 ADMIN_PASSWORD，且 $DATA_DIR/admin_users.json 不存在。"
fi

cleanup() {
  info "开始执行清理：移除临时容器与临时目录"
  docker rm -f "$TMP_NEW_CONTAINER" "$TMP_OLD_CONTAINER" >/dev/null 2>&1 || true
  rm -rf "$TMP_DATA_DIR" "$TMP_OLD_DATA_DIR" "$TMP_PAGES_DIR" "$TMP_OLD_PAGES_DIR"
  info "清理完成"
}
trap cleanup EXIT

phase "开始执行站点升级"
info "YX_ROOT=$YX_ROOT"
info "NETWORK_NAME=$NETWORK_NAME"
info "SYNC_DATA_MODE=$SYNC_DATA_MODE"
info "SYNC_PAGES_MODE=$SYNC_PAGES_MODE"
info "WEBSITE_IMAGE=$WEBSITE_IMAGE"
info "GATEWAY_IMAGE=$GATEWAY_IMAGE"
info "当前运行模式说明：smart=三方合并，additive=只新增，skip=跳过"
if [[ -n "$EXISTING_IMAGE_REF" ]]; then
  info "当前网站容器所用镜像 ID：$EXISTING_IMAGE_REF"
else
  info "当前网站容器所用镜像 ID：<无，可能是首次部署>"
fi

phase "准备目录和 Docker 网络"
mkdir -p "$DATA_DIR" "$PAGES_DIR"
if docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
  info "Docker 网络已存在：$NETWORK_NAME"
else
  info "Docker 网络不存在，正在创建：$NETWORK_NAME"
  docker network create "$NETWORK_NAME" >/dev/null
  info "Docker 网络创建完成：$NETWORK_NAME"
fi
info "数据目录已就绪：$DATA_DIR"
info "页面目录已就绪：$PAGES_DIR"
log_tree_state "数据目录初始化状态" "$DATA_DIR"
log_tree_state "页面目录初始化状态" "$PAGES_DIR"

if ! bool_true "$SKIP_PULL"; then
  phase "拉取最新镜像"
  info "正在拉取网站镜像：$WEBSITE_IMAGE"
  info "下面会显示 Docker 原生镜像拉取进度，请等待拉取完成"
  docker pull "$WEBSITE_IMAGE"
  info "网站镜像拉取完成"
  info "正在拉取网关镜像：$GATEWAY_IMAGE"
  info "下面会显示 Docker 原生镜像拉取进度，请等待拉取完成"
  docker pull "$GATEWAY_IMAGE"
  info "网关镜像拉取完成"
else
  phase "跳过镜像拉取"
  info "SKIP_PULL=$SKIP_PULL"
fi

if [[ "$SYNC_DATA_MODE" != "skip" ]]; then
  sync_image_tree "data 目录" "/app/data" "$DATA_DIR" "$DATA_BASELINE_DIR" "$DATA_CONFLICTS_DIR" "$TMP_DATA_DIR" "$TMP_OLD_DATA_DIR" "$SYNC_DATA_MODE"
else
  phase "跳过 data 目录同步"
  info "SYNC_DATA_MODE=skip"
fi

if [[ "$SYNC_PAGES_MODE" != "skip" ]]; then
  sync_image_tree "pages 目录" "/app/pages" "$PAGES_DIR" "$PAGES_BASELINE_DIR" "$PAGES_CONFLICTS_DIR" "$TMP_PAGES_DIR" "$TMP_OLD_PAGES_DIR" "$SYNC_PAGES_MODE"
else
  phase "跳过 pages 目录同步"
  info "SYNC_PAGES_MODE=skip"
fi

phase "重建容器"
info "开始检查并移除旧容器"
remove_container_if_exists "$GATEWAY_CONTAINER"
remove_container_if_exists "$WEBSITE_CONTAINER"
info "旧容器检查与清理完成"

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
info "正在启动网站容器：$WEBSITE_CONTAINER"
info "网站容器挂载：$DATA_DIR -> /app/data"
info "网站容器挂载：$PAGES_DIR -> /app/pages"
info "网站容器网络：$NETWORK_NAME，网络别名：$WEBSITE_CONTAINER"
info "网站容器环境：APP_ENV、PUBLIC_BASE_URL、TRUST_PROXY_HEADERS、SESSION_COOKIE_SECURE、ADMIN_USERNAME、CDN_ENABLED、TURNSTILE_ENABLED"
WEBSITE_CONTAINER_ID="$("${website_cmd[@]}")"
info "网站容器启动成功，容器 ID：${WEBSITE_CONTAINER_ID:0:12}"

gateway_cmd=(
  docker run -d
  --name "$GATEWAY_CONTAINER"
  --restart unless-stopped
  --network "$NETWORK_NAME"
  -p "127.0.0.1:${MAIN_PORT}:80"
  -p "127.0.0.1:${CDN_PORT}:81"
  "$GATEWAY_IMAGE"
)
info "正在启动网关容器：$GATEWAY_CONTAINER"
info "网关容器端口映射：127.0.0.1:${MAIN_PORT} -> 80"
info "网关容器端口映射：127.0.0.1:${CDN_PORT} -> 81"
info "网关容器网络：$NETWORK_NAME"
GATEWAY_CONTAINER_ID="$("${gateway_cmd[@]}")"
info "网关容器启动成功，容器 ID：${GATEWAY_CONTAINER_ID:0:12}"

phase "验证容器运行状态"
for c in "$WEBSITE_CONTAINER" "$GATEWAY_CONTAINER"; do
  if ! docker ps --filter "name=^/${c}$" --format '{{.Names}}' | grep -qx "$c"; then
    die "容器 '$c' 未正常运行，请执行 docker logs $c 查看原因。"
  fi
  info "容器运行正常：$c"
  info "容器详情摘要：$(docker ps --filter "name=^/${c}$" --format '{{.Names}} | {{.Image}} | {{.Status}}')"
done

if bool_true "$CLEAN_OLD_IMAGES"; then
  phase "清理无用旧镜像"
  docker image prune -f >/dev/null || log "警告：执行 docker image prune 失败，可稍后手动清理。"
  info "无用旧镜像清理完成"
else
  phase "跳过旧镜像清理"
  info "CLEAN_OLD_IMAGES=$CLEAN_OLD_IMAGES"
fi

phase "升级完成"
info "主站入口：http://127.0.0.1:${MAIN_PORT}"
info "CDN 入口：http://127.0.0.1:${CDN_PORT}"
