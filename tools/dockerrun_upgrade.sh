#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

phase() {
  printf '\n' >&2
  log "==> $*"
}

info() {
  log "    $*"
}

warn() {
  log "警告：$*"
}

die() {
  log "错误：$*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令：$1"
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

bool_true() {
  case "$(trim "${1:-}")" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
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

has_regular_files() {
  local dir="$1"
  [[ -d "$dir" ]] || return 1
  find "$dir" -type f -print -quit 2>/dev/null | grep -q .
}

log_tree_state() {
  local label="$1"
  local dir="$2"
  info "[$label] 目录：$dir"
  info "[$label] 文件数：$(count_regular_files "$dir")，总条目数：$(count_all_entries "$dir")"
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

normalize_public_base_url() {
  local value
  value="$(trim "${1:-}")"

  if [[ -z "$value" ]]; then
    printf ''
    return 0
  fi

  if [[ ! "$value" =~ ^https?:// ]]; then
    value="https://$value"
  fi

  value="${value%/}"
  if [[ "$value" =~ ^https?://[^/[:space:]]+$ ]]; then
    printf '%s' "$value"
    return 0
  fi

  printf ''
}

normalize_deploy_strategy() {
  case "$(trim "${1:-}")" in
    smart|SMART|merge|MERGE|1|update|UPDATE)
      printf 'smart'
      ;;
    reset|RESET|fresh|FRESH|rebuild|REBUILD|2)
      printf 'reset'
      ;;
    '')
      printf ''
      ;;
    *)
      die "不支持的 DEPLOY_STRATEGY：'${1:-}'（可选：smart|reset）"
      ;;
  esac
}

prompt_line() {
  local prompt="$1"
  local default_value="${2:-}"
  local secret="${3:-false}"
  local input=""

  [[ -r /dev/tty ]] || die "当前脚本需要交互输入，但未检测到可用终端。请直接在服务器终端执行，或通过环境变量预先传入参数。"

  if [[ -n "$default_value" ]]; then
    printf '%s [%s]: ' "$prompt" "$default_value" >&2
  else
    printf '%s: ' "$prompt" >&2
  fi

  if [[ "$secret" == "true" ]]; then
    IFS= read -r -s input < /dev/tty || die "读取输入失败。"
    printf '\n' >&2
  else
    IFS= read -r input < /dev/tty || die "读取输入失败。"
  fi

  input="$(trim "$input")"
  if [[ -z "$input" && -n "$default_value" ]]; then
    input="$default_value"
  fi

  printf '%s' "$input"
}

prompt_confirm_secret() {
  local prompt="$1"
  local min_len="${2:-1}"
  local first=""
  local second=""

  while true; do
    first="$(prompt_line "$prompt" "" true)"
    if (( ${#first} < min_len )); then
      warn "输入长度不足，至少需要 $min_len 位。"
      continue
    fi

    second="$(prompt_line "请再次输入以确认" "" true)"
    if [[ "$first" != "$second" ]]; then
      warn "两次输入不一致，请重新输入。"
      continue
    fi

    printf '%s' "$first"
    return 0
  done
}

choose_update_strategy() {
  local answer=""

  printf '\n' >&2
  printf '检测到当前机器上已经存在部署痕迹，本次属于“更新部署”。\n' >&2
  printf '请选择更新方式：\n' >&2
  printf '  1) 智能合并更新（默认）\n' >&2
  printf '     保留宿主机已修改的 data/pages 文件；如镜像和宿主机同时改了同一文件，会保留宿主机版本，并把镜像版本存到冲突目录。\n' >&2
  printf '     说明：这种方式最适合保留客户数据和客户改动，但智能合并依然可能遇到误判或需要人工核对的情况。\n' >&2
  printf '  2) 全新部署重置\n' >&2
  printf '     会先备份当前宿主机内容，然后清空 data/pages，以及旧版遗留的 cdn_assets/update_logs 宿主机目录，再把新镜像内容完整导入。\n' >&2
  printf '     说明：这种方式会把宿主机现有客户数据和客户改动整体替换掉，只适合确认要“按新版本重来”时使用。\n' >&2

  while true; do
    answer="$(prompt_line "请输入 1 或 2" "1" false)"
    case "$answer" in
      1) printf 'smart'; return 0 ;;
      2) printf 'reset'; return 0 ;;
      *) warn "输入无效，请输入 1 或 2。" ;;
    esac
  done
}

confirm_reset_action() {
  local answer=""

  printf '\n' >&2
  printf '你选择了“全新部署重置”。这一步属于高风险操作。\n' >&2
  printf '脚本会先备份宿主机当前目录，然后删除以下内容并重新导入新镜像内容：\n' >&2
  printf '  - %s\n' "$DATA_DIR" >&2
  printf '  - %s\n' "$PAGES_DIR" >&2
  printf '  - %s（若存在，仅清理旧部署残留）\n' "$LEGACY_CDN_DIR" >&2
  printf '  - %s（若存在，仅清理旧部署残留）\n' "$LEGACY_UPDATE_LOGS_DIR" >&2
  printf '这意味着客户后台数据、留言、上传文件、页面手工修改都将被新版本内容替换。\n' >&2

  answer="$(prompt_line "如确认继续，请输入 RESET" "" false)"
  [[ "$answer" == "RESET" ]] || die "未输入 RESET，已取消全新部署重置。"
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

refresh_baseline_dir() {
  local label="$1"
  local src_dir="$2"
  local baseline_dir="$3"

  info "正在刷新 ${label} 的本地镜像基线：$baseline_dir"
  rm -rf "$baseline_dir"
  mkdir -p "$baseline_dir"
  rsync -a --delete "$src_dir/" "$baseline_dir/"
  log_tree_state "${label}刷新后的本地基线" "$baseline_dir"
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

  log "$label 智能合并结果：新增 $added 个，更新 $updated 个，保留本地 $kept_local 个，相同 $identical 个，冲突 $conflicts 个，上游删除但本地保留 $upstream_removed 个"
  if (( conflicts > 0 )); then
    warn "$label 存在冲突，新镜像版本已保存到 $conflicts_dir，请上线后人工核对。"
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
      log_file_action "$label" "宿主机已存在该文件，按补充模式跳过" "$rel"
    fi
  done < <(find "$new_dir" -type f -print0)

  log "$label 补充模式结果：新增 $added 个，跳过已存在文件 $skipped 个"
}

sync_image_tree() {
  local label="$1"
  local slug="$2"
  local source_path="$3"
  local host_dir="$4"
  local baseline_dir="$5"
  local conflicts_dir="$6"
  local tmp_new_dir="$7"
  local tmp_old_dir="$8"

  phase "开始处理 ${label}"
  log_tree_state "${label}宿主机当前状态" "$host_dir"

  info "正在从新镜像导出 ${label}：$WEBSITE_IMAGE -> $source_path"
  export_image_tree "$WEBSITE_IMAGE" "$TMP_NEW_CONTAINER-$slug" "$source_path" "$tmp_new_dir" || die "无法从镜像 $WEBSITE_IMAGE 导出 $source_path"
  log_tree_state "${label}新镜像导出结果" "$tmp_new_dir"

  local base_source=""
  local base_label=""
  if [[ -n "$EXISTING_IMAGE_REF" ]]; then
    info "正在导出上一版镜像中的 ${label} 作为智能合并基线"
    if export_image_tree "$EXISTING_IMAGE_REF" "$TMP_OLD_CONTAINER-$slug" "$source_path" "$tmp_old_dir"; then
      base_source="$tmp_old_dir"
      base_label="上一版镜像"
      log_tree_state "${label}上一版镜像基线" "$tmp_old_dir"
    else
      warn "无法从上一版镜像导出 ${label} 基线，将继续尝试使用本地保存基线。"
    fi
  fi

  if [[ -z "$base_source" ]] && has_regular_files "$baseline_dir"; then
    base_source="$baseline_dir"
    base_label="本地保存基线"
    log_tree_state "${label}本地保存基线" "$baseline_dir"
  fi

  if [[ -n "$base_source" ]]; then
    info "将对 ${label} 执行智能合并，基线来源：$base_label"
    smart_merge_tree "$label" "$base_source" "$tmp_new_dir" "$host_dir" "$conflicts_dir"
  else
    warn "当前没有可用智能合并基线，${label} 将退化为“只补充缺失文件”模式。"
    additive_sync_tree "$label" "$tmp_new_dir" "$host_dir"
  fi

  refresh_baseline_dir "$label" "$tmp_new_dir" "$baseline_dir"
  if has_regular_files "$conflicts_dir"; then
    log_tree_state "${label}冲突文件目录" "$conflicts_dir"
  else
    info "${label} 未发现冲突文件。"
  fi
  log_tree_state "${label}同步后的宿主机状态" "$host_dir"
}

backup_dir_if_exists() {
  local src="$1"
  local backup_root="$2"
  local label="$3"

  if [[ -d "$src" ]] && (( $(count_all_entries "$src") > 0 )); then
    info "正在备份 $src -> $backup_root/$label"
    mkdir -p "$backup_root/$label"
    rsync -a "$src/" "$backup_root/$label/"
    info "备份完成：$backup_root/$label"
  else
    info "无需备份：$src 不存在或为空"
  fi
}

reset_host_content_from_image() {
  local backup_root="$1"

  phase "执行全新部署内容重置"
  if [[ -n "$backup_root" ]]; then
    info "本次会先备份旧内容，备份目录：$backup_root"
    backup_dir_if_exists "$DATA_DIR" "$backup_root" "data"
    backup_dir_if_exists "$PAGES_DIR" "$backup_root" "pages"
    backup_dir_if_exists "$LEGACY_CDN_DIR" "$backup_root" "legacy_cdn_assets"
    backup_dir_if_exists "$LEGACY_UPDATE_LOGS_DIR" "$backup_root" "legacy_update_logs"
  else
    info "当前属于首次部署，无需备份旧内容。"
  fi

  for path in \
    "$DATA_DIR" \
    "$PAGES_DIR" \
    "$LEGACY_CDN_DIR" \
    "$LEGACY_UPDATE_LOGS_DIR" \
    "$DATA_BASELINE_DIR" \
    "$DATA_CONFLICTS_DIR" \
    "$PAGES_BASELINE_DIR" \
    "$PAGES_CONFLICTS_DIR"; do
    if [[ -e "$path" ]]; then
      info "正在删除旧目录：$path"
      rm -rf "$path"
      info "已删除：$path"
    else
      info "无需删除：$path 不存在"
    fi
  done

  mkdir -p "$DATA_DIR" "$PAGES_DIR"
  info "开始导入新镜像 data 目录到宿主机"
  rsync -a "$TMP_DATA_DIR/" "$DATA_DIR/"
  info "开始导入新镜像 pages 目录到宿主机"
  rsync -a "$TMP_PAGES_DIR/" "$PAGES_DIR/"

  refresh_baseline_dir "data 目录" "$TMP_DATA_DIR" "$DATA_BASELINE_DIR"
  refresh_baseline_dir "pages 目录" "$TMP_PAGES_DIR" "$PAGES_BASELINE_DIR"

  info "说明：当前架构不再宿主机挂载 cdn_assets / update_logs，后续将直接使用镜像内文件。"
  log_tree_state "全新部署后的 data 目录状态" "$DATA_DIR"
  log_tree_state "全新部署后的 pages 目录状态" "$PAGES_DIR"
}

pick_value() {
  local key="$1"
  local default_value="$2"
  local value=""

  PICKED_VALUE_SOURCE=""
  value="$(trim "${!key-}")"
  if [[ -n "$value" ]]; then
    PICKED_VALUE_SOURCE="当前 shell 环境变量"
    printf '%s' "$value"
    return 0
  fi

  value="$(get_existing_env "$key")"
  if [[ -n "$value" ]]; then
    PICKED_VALUE_SOURCE="旧网站容器环境变量"
    printf '%s' "$value"
    return 0
  fi

  PICKED_VALUE_SOURCE="脚本默认值"
  printf '%s' "$default_value"
}

get_existing_env() {
  local key="$1"
  if [[ -z "${EXISTING_ENV_LINES:-}" ]]; then
    return 0
  fi
  awk -F= -v k="$key" '$1==k { $1=""; sub(/^=/, ""); print; exit }' <<< "$EXISTING_ENV_LINES" | while IFS= read -r line; do
    printf '%s' "$(trim "$line")"
  done
}

resolve_basic_runtime_values() {
  APP_ENV_VAL="$(pick_value APP_ENV production)"
  info "APP_ENV=$APP_ENV_VAL（来源：$PICKED_VALUE_SOURCE）"

  ADMIN_USERNAME_VAL="$(pick_value ADMIN_USERNAME admin)"
  info "ADMIN_USERNAME=$ADMIN_USERNAME_VAL（来源：$PICKED_VALUE_SOURCE）"

  TRUST_PROXY_HEADERS_VAL="$(pick_value TRUST_PROXY_HEADERS true)"
  info "TRUST_PROXY_HEADERS=$TRUST_PROXY_HEADERS_VAL（来源：$PICKED_VALUE_SOURCE）"

  SESSION_COOKIE_SECURE_VAL="$(pick_value SESSION_COOKIE_SECURE true)"
  info "SESSION_COOKIE_SECURE=$SESSION_COOKIE_SECURE_VAL（来源：$PICKED_VALUE_SOURCE）"

  CDN_ENABLED_VAL="$(pick_value CDN_ENABLED false)"
  CDN_DOMAIN_VAL="$(pick_value CDN_DOMAIN "")"
  TURNSTILE_ENABLED_VAL="$(pick_value TURNSTILE_ENABLED false)"
  TURNSTILE_SITE_KEY_VAL="$(pick_value TURNSTILE_SITE_KEY "")"
  TURNSTILE_SECRET_KEY_VAL="$(pick_value TURNSTILE_SECRET_KEY "")"
}

resolve_secret_key() {
  local value=""
  local source=""

  value="$(pick_value SECRET_KEY "")"
  source="$PICKED_VALUE_SOURCE"

  if [[ -n "$value" && ${#value} -lt 32 ]]; then
    warn "检测到的 SECRET_KEY 长度不足 32 位，将改为交互输入。"
    value=""
    source=""
  fi

  if [[ -z "$value" ]]; then
    value="$(prompt_confirm_secret "请输入 SECRET_KEY（至少 32 位，生产环境务必固定不变）" 32)"
    source="交互输入"
  fi

  SECRET_KEY_VAL="$value"
  info "SECRET_KEY 已确认（来源：$source，长度：${#SECRET_KEY_VAL}）"
}

resolve_public_base_url() {
  local value=""
  local normalized=""
  local source=""

  value="$(pick_value PUBLIC_BASE_URL "")"
  source="$PICKED_VALUE_SOURCE"
  normalized="$(normalize_public_base_url "$value")"

  if [[ -z "$normalized" ]]; then
    while true; do
      value="$(prompt_line "请输入站点公开访问地址，例如 https://test.hnmetachip.cn" "$value" false)"
      normalized="$(normalize_public_base_url "$value")"
      if [[ -n "$normalized" ]]; then
        source="交互输入"
        break
      fi
      warn "PUBLIC_BASE_URL 格式无效，请输入带域名的 http/https 地址。"
    done
  fi

  PUBLIC_BASE_URL_VAL="$normalized"
  info "PUBLIC_BASE_URL=$PUBLIC_BASE_URL_VAL（来源：$source）"
}

resolve_admin_bootstrap_if_needed() {
  ADMIN_PASSWORD_HASH_VAL="$(trim "${ADMIN_PASSWORD_HASH-}")"
  ADMIN_PASSWORD_VAL="$(trim "${ADMIN_PASSWORD-}")"

  if [[ -s "$DATA_DIR/admin_users.json" ]]; then
    info "检测到 $DATA_DIR/admin_users.json 已存在，跳过超级管理员初始化。"
    ADMIN_PASSWORD_HASH_VAL=""
    ADMIN_PASSWORD_VAL=""
    return 0
  fi

  phase "初始化超级管理员"
  info "当前宿主机 data 目录中不存在 admin_users.json，本次需要初始化超级管理员账号。"
  info "管理员账号名将使用：$ADMIN_USERNAME_VAL"

  if [[ -n "$ADMIN_PASSWORD_HASH_VAL" ]]; then
    info "检测到外部已提供 ADMIN_PASSWORD_HASH，将使用提供的哈希值初始化管理员。"
    return 0
  fi

  if [[ -n "$ADMIN_PASSWORD_VAL" ]]; then
    info "检测到外部已提供 ADMIN_PASSWORD，将使用提供的明文密码初始化管理员。"
    return 0
  fi

  ADMIN_PASSWORD_VAL="$(prompt_confirm_secret "请输入超级管理员初始密码（至少 6 位）" 6)"
  info "超级管理员初始密码已通过交互输入获取。"
}

load_existing_state() {
  HAS_WEBSITE_CONTAINER=false
  HAS_GATEWAY_CONTAINER=false
  EXISTING_ENV_LINES=""
  EXISTING_IMAGE_REF=""

  if docker container inspect "$WEBSITE_CONTAINER" >/dev/null 2>&1; then
    HAS_WEBSITE_CONTAINER=true
    EXISTING_ENV_LINES="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$WEBSITE_CONTAINER" || true)"
    EXISTING_IMAGE_REF="$(docker inspect -f '{{.Image}}' "$WEBSITE_CONTAINER" || true)"
  fi

  if docker container inspect "$GATEWAY_CONTAINER" >/dev/null 2>&1; then
    HAS_GATEWAY_CONTAINER=true
  fi

  DATA_FILE_COUNT="$(count_regular_files "$DATA_DIR")"
  PAGES_FILE_COUNT="$(count_regular_files "$PAGES_DIR")"
  LEGACY_CDN_FILE_COUNT="$(count_regular_files "$LEGACY_CDN_DIR")"
  LEGACY_UPDATE_LOGS_FILE_COUNT="$(count_regular_files "$LEGACY_UPDATE_LOGS_DIR")"

  HAS_HOST_CONTENT=false
  if [[ "$DATA_FILE_COUNT" != "0" || "$PAGES_FILE_COUNT" != "0" || "$LEGACY_CDN_FILE_COUNT" != "0" || "$LEGACY_UPDATE_LOGS_FILE_COUNT" != "0" ]]; then
    HAS_HOST_CONTENT=true
  fi
}

determine_deploy_kind_and_strategy() {
  phase "识别部署场景"
  info "website 容器是否存在：$HAS_WEBSITE_CONTAINER"
  info "gateway 容器是否存在：$HAS_GATEWAY_CONTAINER"
  info "宿主机 data 文件数：$DATA_FILE_COUNT"
  info "宿主机 pages 文件数：$PAGES_FILE_COUNT"
  info "旧版宿主机 cdn_assets 文件数：$LEGACY_CDN_FILE_COUNT"
  info "旧版宿主机 update_logs 文件数：$LEGACY_UPDATE_LOGS_FILE_COUNT"

  if [[ "$HAS_WEBSITE_CONTAINER" == "true" || "$HAS_GATEWAY_CONTAINER" == "true" || "$HAS_HOST_CONTENT" == "true" ]]; then
    DEPLOY_KIND="update"
    info "判断结果：当前机器上已存在部署痕迹，本次按“更新部署”处理。"
  else
    DEPLOY_KIND="fresh"
    info "判断结果：当前机器上未发现部署痕迹，本次按“首次部署”处理。"
  fi

  if [[ "$DEPLOY_KIND" == "fresh" ]]; then
    DEPLOY_STRATEGY_MODE="reset"
    info "首次部署无需选择更新策略，将自动按“全新初始化导入”执行。"
    return 0
  fi

  DEPLOY_STRATEGY_MODE="$(normalize_deploy_strategy "${DEPLOY_STRATEGY:-}")"
  if [[ -n "$DEPLOY_STRATEGY_MODE" ]]; then
    info "检测到外部指定 DEPLOY_STRATEGY=$DEPLOY_STRATEGY_MODE，本次将按指定策略执行。"
  else
    DEPLOY_STRATEGY_MODE="$(choose_update_strategy)"
  fi

  if [[ "$DEPLOY_STRATEGY_MODE" == "reset" ]]; then
    confirm_reset_action
  fi
}

prepare_directories_and_network() {
  phase "准备目录和 Docker 网络"
  mkdir -p "$DATA_DIR" "$PAGES_DIR"

  if docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    info "Docker 网络已存在：$NETWORK_NAME"
  else
    info "Docker 网络不存在，正在创建：$NETWORK_NAME"
    docker network create "$NETWORK_NAME" >/dev/null
    info "Docker 网络创建完成：$NETWORK_NAME"
  fi

  log_tree_state "data 目录初始化状态" "$DATA_DIR"
  log_tree_state "pages 目录初始化状态" "$PAGES_DIR"
}

pull_latest_images() {
  phase "拉取最新镜像"
  info "正在拉取网站镜像：$WEBSITE_IMAGE"
  info "下面会显示 Docker 原生镜像拉取进度，请等待拉取完成。"
  docker pull "$WEBSITE_IMAGE"
  info "网站镜像拉取完成。"

  info "正在拉取网关镜像：$GATEWAY_IMAGE"
  info "下面会显示 Docker 原生镜像拉取进度，请等待拉取完成。"
  docker pull "$GATEWAY_IMAGE"
  info "网关镜像拉取完成。"
}

prepare_content_for_fresh_or_reset() {
  phase "准备首次部署 / 全新重置所需的新版本内容"
  export_image_tree "$WEBSITE_IMAGE" "$TMP_NEW_CONTAINER-data" "/app/data" "$TMP_DATA_DIR" || die "无法从新镜像导出 /app/data"
  export_image_tree "$WEBSITE_IMAGE" "$TMP_NEW_CONTAINER-pages" "/app/pages" "$TMP_PAGES_DIR" || die "无法从新镜像导出 /app/pages"
  log_tree_state "新镜像 data 导出结果" "$TMP_DATA_DIR"
  log_tree_state "新镜像 pages 导出结果" "$TMP_PAGES_DIR"

  local backup_root=""
  if [[ "$DEPLOY_KIND" == "update" && "$DEPLOY_STRATEGY_MODE" == "reset" ]]; then
    backup_root="$YX_ROOT/backups/reset-$(date '+%Y%m%d-%H%M%S')"
  fi

  reset_host_content_from_image "$backup_root"
}

prepare_content_for_smart_update() {
  sync_image_tree "data 目录" "data" "/app/data" "$DATA_DIR" "$DATA_BASELINE_DIR" "$DATA_CONFLICTS_DIR" "$TMP_DATA_DIR" "$TMP_OLD_DATA_DIR"
  sync_image_tree "pages 目录" "pages" "/app/pages" "$PAGES_DIR" "$PAGES_BASELINE_DIR" "$PAGES_CONFLICTS_DIR" "$TMP_PAGES_DIR" "$TMP_OLD_PAGES_DIR"
}

recreate_containers() {
  phase "重建容器"
  info "开始检查并移除旧容器。"
  remove_container_if_exists "$GATEWAY_CONTAINER"
  remove_container_if_exists "$WEBSITE_CONTAINER"

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
  info "网站容器网络：$NETWORK_NAME，网络别名：$WEBSITE_CONTAINER"
  info "网站容器挂载：$DATA_DIR -> /app/data"
  info "网站容器挂载：$PAGES_DIR -> /app/pages"
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
  GATEWAY_CONTAINER_ID="$("${gateway_cmd[@]}")"
  info "网关容器启动成功，容器 ID：${GATEWAY_CONTAINER_ID:0:12}"
}

verify_containers() {
  phase "验证容器运行状态"
  for c in "$WEBSITE_CONTAINER" "$GATEWAY_CONTAINER"; do
    if ! docker ps --filter "name=^/${c}$" --format '{{.Names}}' | grep -qx "$c"; then
      die "容器 '$c' 未正常运行，请执行 docker logs $c 查看原因。"
    fi
    info "容器运行正常：$c"
    info "容器详情摘要：$(docker ps --filter "name=^/${c}$" --format '{{.Names}} | {{.Image}} | {{.Status}}')"
  done
}

cleanup_old_images() {
  if bool_true "$CLEAN_OLD_IMAGES"; then
    phase "清理无用旧镜像"
    docker image prune -f >/dev/null || warn "执行 docker image prune 失败，可稍后手动清理。"
    info "无用旧镜像清理完成。"
  else
    phase "跳过旧镜像清理"
    info "CLEAN_OLD_IMAGES=$CLEAN_OLD_IMAGES"
  fi
}

cleanup() {
  docker rm -f \
    "${TMP_NEW_CONTAINER}-data" \
    "${TMP_NEW_CONTAINER}-pages" \
    "${TMP_OLD_CONTAINER}-data" \
    "${TMP_OLD_CONTAINER}-pages" >/dev/null 2>&1 || true
  rm -rf "$TMP_DATA_DIR" "$TMP_OLD_DATA_DIR" "$TMP_PAGES_DIR" "$TMP_OLD_PAGES_DIR"
}

show_help() {
  cat <<'USAGE'
用法：
  bash tools/dockerrun_upgrade.sh

推荐用途：
  这是网站 Docker 部署/升级的首选脚本。
  它会自动识别当前机器是“首次部署”还是“更新部署”，并在更新时让你选择：
  1. 智能合并更新
  2. 全新部署重置

可选环境变量：
  YX_ROOT=/root/yxwebsite
  NETWORK_NAME=yx-net
  WEBSITE_CONTAINER=yx-website
  GATEWAY_CONTAINER=yx-gateway
  WEBSITE_IMAGE=ghcr.io/zhizinan1997/yx_website:latest
  GATEWAY_IMAGE=ghcr.io/zhizinan1997/yx-gateway:latest
  MAIN_PORT=2026
  CDN_PORT=2027
  CLEAN_OLD_IMAGES=true
  DEPLOY_STRATEGY=smart|reset

交互说明：
  - 首次部署：脚本会自动导入新镜像里的 data/pages 内容，并要求输入 SECRET_KEY、PUBLIC_BASE_URL；如果还没有 admin_users.json，也会要求输入管理员初始密码。
  - 更新部署：脚本会先让你选择“智能合并更新”或“全新部署重置”。
  - 如果旧容器仍存在，脚本会优先复用旧容器中的 SECRET_KEY、PUBLIC_BASE_URL 等环境变量。
  - 如果缺少这些环境变量，脚本会直接在终端里提示输入。

风险说明：
  - “智能合并更新”会尽量保留宿主机已修改内容，但冲突文件仍可能需要人工核对。
  - “全新部署重置”会先备份再清空宿主机 data/pages 和旧版残留目录，再导入新镜像内容，客户数据和客户改动都会被替换。
USAGE
}

# 默认值
YX_ROOT="${YX_ROOT:-/root/yxwebsite}"
NETWORK_NAME="${NETWORK_NAME:-yx-net}"
WEBSITE_CONTAINER="${WEBSITE_CONTAINER:-yx-website}"
GATEWAY_CONTAINER="${GATEWAY_CONTAINER:-yx-gateway}"
WEBSITE_IMAGE="${WEBSITE_IMAGE:-ghcr.io/zhizinan1997/yx_website:latest}"
GATEWAY_IMAGE="${GATEWAY_IMAGE:-ghcr.io/zhizinan1997/yx-gateway:latest}"
MAIN_PORT="${MAIN_PORT:-2026}"
CDN_PORT="${CDN_PORT:-2027}"
CLEAN_OLD_IMAGES="${CLEAN_OLD_IMAGES:-true}"

DATA_DIR="$YX_ROOT/data"
PAGES_DIR="$YX_ROOT/pages"
LEGACY_CDN_DIR="$YX_ROOT/cdn_assets"
LEGACY_UPDATE_LOGS_DIR="$YX_ROOT/update_logs"
DATA_BASELINE_DIR="$YX_ROOT/.data-image-baseline"
PAGES_BASELINE_DIR="$YX_ROOT/.pages-image-baseline"
DATA_CONFLICTS_DIR="$YX_ROOT/.data-merge-conflicts"
PAGES_CONFLICTS_DIR="$YX_ROOT/.pages-merge-conflicts"
TMP_DATA_DIR="$YX_ROOT/.tmp-data"
TMP_OLD_DATA_DIR="$YX_ROOT/.tmp-data-old"
TMP_PAGES_DIR="$YX_ROOT/.tmp-pages"
TMP_OLD_PAGES_DIR="$YX_ROOT/.tmp-pages-old"
TMP_NEW_CONTAINER="yx-website-export-new-$(date +%s)-$$"
TMP_OLD_CONTAINER="yx-website-export-old-$(date +%s)-$$"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  show_help
  exit 0
fi

trap cleanup EXIT

require_cmd docker
require_cmd rsync

if [[ -z "$YX_ROOT" || "$YX_ROOT" == "/" ]]; then
  die "YX_ROOT 无效：'$YX_ROOT'"
fi

phase "开始执行站点部署脚本"
info "脚本目标目录：$YX_ROOT"
info "网站镜像：$WEBSITE_IMAGE"
info "网关镜像：$GATEWAY_IMAGE"
info "主站端口：$MAIN_PORT"
info "CDN 端口：$CDN_PORT"

load_existing_state
determine_deploy_kind_and_strategy
resolve_basic_runtime_values
resolve_secret_key
resolve_public_base_url
prepare_directories_and_network
pull_latest_images

if [[ "$DEPLOY_KIND" == "fresh" || "$DEPLOY_STRATEGY_MODE" == "reset" ]]; then
  prepare_content_for_fresh_or_reset
else
  prepare_content_for_smart_update
fi

resolve_admin_bootstrap_if_needed
recreate_containers
verify_containers
cleanup_old_images

phase "部署完成"
info "部署类型：$DEPLOY_KIND"
if [[ "$DEPLOY_KIND" == "update" ]]; then
  info "本次更新策略：$DEPLOY_STRATEGY_MODE"
fi
info "主站入口：http://127.0.0.1:${MAIN_PORT}"
info "CDN 入口：http://127.0.0.1:${CDN_PORT}"
if has_regular_files "$DATA_CONFLICTS_DIR"; then
  warn "检测到 data 合并冲突，请检查：$DATA_CONFLICTS_DIR"
fi
if has_regular_files "$PAGES_CONFLICTS_DIR"; then
  warn "检测到 pages 合并冲突，请检查：$PAGES_CONFLICTS_DIR"
fi
