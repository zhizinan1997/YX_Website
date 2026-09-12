#!/usr/bin/env bash
set -Eeuo pipefail

supports_color() {
  [[ -t 2 ]] || return 1
  [[ -n "${NO_COLOR:-}" ]] && return 1
  [[ "${TERM:-}" == "dumb" ]] && return 1
}

if supports_color; then
  STYLE_RESET=$'\033[0m'
  STYLE_BOLD=$'\033[1m'
  STYLE_DIM=$'\033[2m'
  STYLE_RED=$'\033[31m'
  STYLE_GREEN=$'\033[32m'
  STYLE_YELLOW=$'\033[33m'
  STYLE_BLUE=$'\033[34m'
  STYLE_MAGENTA=$'\033[35m'
  STYLE_CYAN=$'\033[36m'
else
  STYLE_RESET=''
  STYLE_BOLD=''
  STYLE_DIM=''
  STYLE_RED=''
  STYLE_GREEN=''
  STYLE_YELLOW=''
  STYLE_BLUE=''
  STYLE_MAGENTA=''
  STYLE_CYAN=''
fi

print_rule() {
  printf '%b%s%b\n' "$STYLE_DIM" '----------------------------------------------------------------------' "$STYLE_RESET" >&2
}

log_with_level() {
  local style="$1"
  local label="$2"
  shift 2

  printf '%b[%s]%b %b[%s]%b %s\n' \
    "$STYLE_DIM" "$(date '+%Y-%m-%d %H:%M:%S')" "$STYLE_RESET" \
    "$style" "$label" "$STYLE_RESET" \
    "$*" >&2
}

log() {
  log_with_level "$STYLE_CYAN" "日志" "$*"
}

phase() {
  printf '\n' >&2
  print_rule
  printf '%b%s%b %s\n' "$STYLE_BLUE$STYLE_BOLD" '==>' "$STYLE_RESET" "$*" >&2
  print_rule
}

info() {
  log_with_level "$STYLE_CYAN" "信息" "$*"
}

success() {
  log_with_level "$STYLE_GREEN$STYLE_BOLD" "完成" "$*"
}

warn() {
  log_with_level "$STYLE_YELLOW$STYLE_BOLD" "警告" "$*"
}

die() {
  log_with_level "$STYLE_RED$STYLE_BOLD" "错误" "$*"
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "缺少命令：$1"
}

trim() {
  local value="$1"
  value="${value//$'\r'/}"
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

# v4.7.0 起应用端会拒绝常见占位密钥；脚本提前识别，避免升级后容器启动失败才暴露。
is_placeholder_secret() {
  local lowered="${1,,}"
  case "$lowered" in
    *change-me*|*changeme*|*replace-with*|*please-change*|*placeholder*|*default-secret*|*my-secret*|*dummy-secret*|*example-secret*|*test-secret*)
      return 0 ;;
    *) return 1 ;;
  esac
}

# 宿主机/容器基础环境，不参与"旧容器变量继承"。
is_system_env_key() {
  case "$1" in
    PATH|HOME|HOSTNAME|PWD|OLDPWD|SHLVL|TERM|LANG|LC_ALL|GPG_KEY|PYTHON_VERSION|PYTHON_PIP_VERSION|PYTHON_SETUPTOOLS_VERSION|PYTHON_GET_PIP_URL|PYTHON_GET_PIP_SHA256|PYTHONDONTWRITEBYTECODE|PYTHONUNBUFFERED|PYTHONPATH|PIP_DISABLE_PIP_VERSION_CHECK|PIP_DEFAULT_TIMEOUT|PIP_ROOT_USER_ACTION|PIP_NO_CACHE_DIR|WERKZEUG_RUN_MAIN)
      return 0 ;;
    *) return 1 ;;
  esac
}

# 脚本托管的变量已单独解析，继承时跳过，避免 docker run 出现重复 -e。
WEBSITE_MANAGED_ENV_KEYS="APP_ENV SECRET_KEY PUBLIC_BASE_URL TRUST_PROXY_HEADERS SESSION_COOKIE_SECURE ADMIN_USERNAME ADMIN_PASSWORD ADMIN_PASSWORD_HASH HIDDEN_ADMIN_USERNAME HIDDEN_ADMIN_PASSWORD HIDDEN_ADMIN_PASSWORD_HASH CDN_ENABLED CDN_DOMAIN TURNSTILE_ENABLED TURNSTILE_SITE_KEY TURNSTILE_SECRET_KEY ADMIN_CAPTCHA_PROVIDER ADMIN_ESA_IDENTITY ADMIN_ESA_SCENE_ID ADMIN_ESA_REGION TURNSTILE_PROXY_URL TURNSTILE_PROXY_FALLBACK_ENABLED ALLOW_WEAK_ADMIN_PASSWORDS APP_VERSION APP_BUILD_TIME PORT DOCKER_CONTAINER_1_NAME DOCKER_LOG_FALLBACK_APP_FILES"

CARRIED_WEBSITE_ENV=()

# 把旧容器里脚本未托管的应用环境变量继承到新容器（v4.4.0 后新增了大量
# 可选环境变量：CHATBOT/PRODUCT_AI/PASSKEY/SMTP/INDEXNOW/BAIDU_PUSH_TOKEN 等，
# 固定清单必然漏掉；同名 shell 环境变量优先，日志只记变量名不记值）。
collect_carried_env_for() {
  local lines="$1"
  local managed_keys="$2"
  local target="$3"
  local line key value source_label

  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    key="${line%%=*}"
    [[ -z "$key" || "$key" == "$line" ]] && continue
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    is_system_env_key "$key" && continue
    [[ " $managed_keys " == *" $key "* ]] && continue
    value="${line#*=}"
    [[ -z "$value" ]] && continue
    if [[ -n "${!key:-}" ]]; then
      value="${!key}"
      source_label="当前 shell 环境变量覆盖"
    else
      source_label="继承自旧容器"
    fi
    CARRIED_WEBSITE_ENV+=( "-e" "${key}=${value}" )
    info "继承环境变量：${key}（${source_label}，值不在日志显示）"
  done <<< "$lines"
}

resolve_carried_env() {
  phase "继承旧容器环境变量"
  collect_carried_env_for "$EXISTING_ENV_LINES" "$WEBSITE_MANAGED_ENV_KEYS" "website"
  if (( ${#CARRIED_WEBSITE_ENV[@]} == 0 )); then
    info "未发现需要继承的额外环境变量。"
  fi
}

# 镜像里仓库版副本与服务器运行时数据不同的文件：不参与智能合并，
# 宿主机已有的一律保留，避免每次升级制造无意义冲突或误覆盖。
is_runtime_merge_excluded() {
  local rel="$1"
  case "$rel" in
    app.log|local-server.stderr.log|local-server.stdout.log|logs/*|\
    .flask_secret_key|config.json|rate_limits.json|\
    image_seo_*.json|site_analytics_*.jsonl|site_analytics_events.jsonl|\
    admin_login_attempts.json|admin_login_logs.json|chatbot_conversation_logs.jsonl)
      return 0 ;;
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
    info "[${label}] ${action}：${rel} -> ${extra}"
  else
    info "[${label}] ${action}：${rel}"
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
    reset-keep-data|RESET-KEEP-DATA|reset_keep_data|3|keep-data|KEEP-DATA|keepdata|KEEPDATA)
      printf 'reset-keep-data'
      ;;
    '')
      printf ''
      ;;
    *)
      die "不支持的 DEPLOY_STRATEGY：'${1:-}'（可选：smart|reset|reset-keep-data）"
      ;;
  esac
}

prompt_line_into() {
  local out_var="$1"
  local prompt="$2"
  local default_value="${3:-}"
  local secret="${4:-false}"
  local input=""

  [[ -r /dev/tty ]] || die "当前脚本需要交互输入，但未检测到可用终端。请直接在服务器终端执行，或通过环境变量预先传入参数。"

  if [[ -n "$default_value" ]]; then
    printf '%b%s%b [%s]: ' "$STYLE_MAGENTA$STYLE_BOLD" "$prompt" "$STYLE_RESET" "$default_value" >&2
  else
    printf '%b%s%b: ' "$STYLE_MAGENTA$STYLE_BOLD" "$prompt" "$STYLE_RESET" >&2
  fi

  if [[ "$secret" == "true" ]]; then
    IFS= read -r -s input < /dev/tty || die "读取输入失败。"
    printf '\n' >&2
  else
    IFS= read -r input < /dev/tty || die "读取输入失败。"
  fi

  input="${input//$'\r'/}"
  input="$(trim "$input")"
  if [[ -z "$input" && -n "$default_value" ]]; then
    input="$default_value"
  fi

  printf -v "$out_var" '%s' "$input"
}

# 高风险操作的确认输入：与一次性确认不同，这里必须容错——
# 宝塔等 web 终端常见"按键已敲但行没进缓冲/回车被吞成空行/中文输入法
# 吞字母"的问题，数字键不受输入法影响，因此确认词一律用数字。
# 空输入给出明确提示并重问（最多 3 次）；显式取消词才终止。
# 注意：接收变量必须叫 reply——prompt_line_into 内部声明了局部变量
# input，若把 out_var 命名为 "input"，读到的值会被留在内层函数里，
# 调用方永远拿到空串（v4.8.2 曾因此导致确认环节必然失败）。
prompt_confirm_word_into() {
  local out_var="$1"
  local prompt="$2"
  local expected_word="$3"
  local cancel_label="$4"
  local attempt=""
  local reply=""

  for attempt in 1 2 3; do
    prompt_line_into reply "$prompt（输入 $expected_word 继续，输入 n 取消）" "" false
    if [[ -z "$reply" ]]; then
      warn "未检测到输入（终端可能吞掉了按键），请重新输入 $expected_word。"
      continue
    fi
    case "$reply" in
      "$expected_word")
        printf -v "$out_var" '%s' "$reply"
        return 0
        ;;
      n|no|q|quit|取消|退出)
        die "已输入取消指令，$cancel_label 已取消。"
        ;;
      *)
        warn "第 $attempt/3 次输入的是「$reply」，与确认数字 $expected_word 不一致（请输入数字，不是字母）。"
        ;;
    esac
  done

  die "连续 3 次未输入正确的确认数字 $expected_word，$cancel_label 已取消。如多次出现按键丢失，建议改用 SSH 终端执行本脚本。"
}

prompt_confirm_secret_into() {
  local out_var="$1"
  local prompt="$2"
  local min_len="${3:-1}"
  local first=""
  local second=""

  while true; do
    prompt_line_into first "$prompt" "" true
    if (( ${#first} < min_len )); then
      warn "输入长度不足，至少需要 $min_len 位。"
      continue
    fi

    prompt_line_into second "请再次输入以确认" "" true
    if [[ "$first" != "$second" ]]; then
      warn "两次输入不一致，请重新输入。"
      continue
    fi

    printf -v "$out_var" '%s' "$first"
    return 0
  done
}

choose_update_strategy() {
  local answer=""

  printf '\n' >&2
  print_rule
  printf '%b%s%b\n' "$STYLE_BLUE$STYLE_BOLD" '更新模式选择' "$STYLE_RESET" >&2
  printf '检测到当前机器上已经存在部署痕迹，本次属于"更新部署"。\n' >&2
  printf '%b%s%b\n' "$STYLE_DIM" '请选择更新方式：' "$STYLE_RESET" >&2
  printf '  %b1)%b 智能合并更新（默认）\n' "$STYLE_GREEN$STYLE_BOLD" "$STYLE_RESET" >&2
  printf '     保留宿主机已修改的 data/pages 文件；如镜像和宿主机同时改了同一文件，会保留宿主机版本，并把镜像版本存到冲突目录。\n' >&2
  printf '     说明：这种方式最适合保留客户数据和客户改动，但智能合并依然可能遇到误判或需要人工核对的情况。\n' >&2
  printf '  %b2)%b 全新部署重置\n' "$STYLE_YELLOW$STYLE_BOLD" "$STYLE_RESET" >&2
  printf '     会先备份当前宿主机内容，然后清空 data/pages，以及旧版遗留的 cdn_assets/update_logs 宿主机目录，再把新镜像内容完整导入。\n' >&2
  printf '     说明：这种方式会把宿主机现有客户数据和客户改动整体替换掉，只适合确认要"按新版本重来"时使用。\n' >&2
  printf '  %b3)%b 重置界面，保留用户数据\n' "$STYLE_CYAN$STYLE_BOLD" "$STYLE_RESET" >&2
  printf '     会先备份当前宿主机内容，然后清空 pages/cdn_assets 并从新镜像重新导入，但完整保留 data 目录不做任何改动。\n' >&2
  printf '     说明：适合界面代码需要完全刷新、但客户后台数据（留言、配置、管理员账号等）必须保留的场景。\n' >&2
  print_rule

  while true; do
    prompt_line_into answer "请输入 1、2 或 3" "1" false
    case "$answer" in
      1)
        # 空输入会落到默认值 1：终端吞按键时用户以为选了 2/3，必须
        # 大声回显实际注册的选择，避免静默走错分支。
        success "已选择：1) 智能合并更新"
        printf 'smart'; return 0
        ;;
      2)
        success "已选择：2) 全新部署重置（稍后需输入数字 2 二次确认）"
        printf 'reset'; return 0
        ;;
      3)
        success "已选择：3) 重置界面，保留用户数据（稍后需输入数字 3 二次确认）"
        printf 'reset-keep-data'; return 0
        ;;
      *)
        warn "输入无效，收到的是「$answer」，请输入 1、2 或 3。"
        ;;
    esac
  done
}

confirm_reset_action() {
  local answer=""

  printf '\n' >&2
  print_rule
  printf '%b%s%b\n' "$STYLE_YELLOW$STYLE_BOLD" '高风险确认：全新部署重置' "$STYLE_RESET" >&2
  printf '你选择了"全新部署重置"。这一步属于高风险操作。\n' >&2
  printf '脚本会先备份宿主机当前目录，然后删除以下内容并重新导入新镜像内容：\n' >&2
  printf '  - %s\n' "$DATA_DIR" >&2
  printf '  - %s\n' "$PAGES_DIR" >&2
  printf '  - %s（若存在，仅清理旧部署残留）\n' "$LEGACY_CDN_DIR" >&2
  printf '  - %s（若存在，仅清理旧部署残留）\n' "$LEGACY_UPDATE_LOGS_DIR" >&2
  printf '%b%s%b\n' "$STYLE_YELLOW" '这意味着客户后台数据、留言、上传文件、页面手工修改都将被新版本内容替换。' "$STYLE_RESET" >&2
  print_rule

  prompt_confirm_word_into answer "如确认继续，请输入数字 2" "2" "全新部署重置"
}

confirm_reset_keep_data_action() {
  local answer=""

  printf '\n' >&2
  print_rule
  printf '%b%s%b\n' "$STYLE_CYAN$STYLE_BOLD" '确认：重置界面，保留用户数据' "$STYLE_RESET" >&2
  printf '你选择了"重置界面，保留用户数据"。\n' >&2
  printf '脚本会先备份以下目录，然后删除并从新镜像重新导入：\n' >&2
  printf '  - %s（删除后重新导入）\n' "$PAGES_DIR" >&2
  printf '  - %s（删除后重新导入）\n' "$CDN_ASSETS_DIR" >&2
  printf '  - %s（若存在，仅清理旧部署残留）\n' "$LEGACY_CDN_DIR" >&2
  printf '  - %s（若存在，仅清理旧部署残留）\n' "$LEGACY_UPDATE_LOGS_DIR" >&2
  printf '\n' >&2
  printf '以下目录将被完整保留，不做任何改动：\n' >&2
  printf '  - %s（用户数据、配置、留言、管理员账号等）\n' "$DATA_DIR" >&2
  print_rule

  prompt_confirm_word_into answer "如确认继续，请输入数字 3" "3" "重置界面（保留用户数据）"
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
    info "检测到已有容器：${name}，正在删除"
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
  local rel="" host_file="" base_file="" new_file=""

  rm -rf "$conflicts_dir"
  mkdir -p "$conflicts_dir"

  while IFS= read -r -d '' new_file; do
    rel="${new_file#$new_dir/}"
    host_file="$host_dir/$rel"
    base_file="$base_dir/$rel"

    if is_runtime_merge_excluded "$rel"; then
      if [[ -e "$host_file" ]]; then
        kept_local=$((kept_local + 1))
        log_file_action "$label" "运行时文件，跳过合并（保留宿主机版本）" "$rel"
      else
        copy_with_parents "$new_file" "$host_file"
        added=$((added + 1))
        log_file_action "$label" "新增运行时文件" "$rel"
      fi
      continue
    fi

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
    rel="${base_file#$base_dir/}"
    new_file="$new_dir/$rel"
    host_file="$host_dir/$rel"

    [[ -e "$new_file" ]] && continue
    [[ -e "$host_file" ]] || continue

    if is_runtime_merge_excluded "$rel"; then
      log_file_action "$label" "运行时文件，跳过上游删除同步" "$rel"
      continue
    fi

    if cmp -s "$host_file" "$base_file"; then
      rm -f "$host_file"
      upstream_removed=$((upstream_removed + 1))
      log_file_action "$label" "新镜像已删除该文件，宿主机版本未修改，同步删除" "$rel"
    else
      log_file_action "$label" "新镜像已删除该文件，但宿主机已修改，保留本地版本" "$rel"
    fi
  done < <(find "$base_dir" -type f -print0)

  log "$label 智能合并结果：新增 $added 个，更新 $updated 个，保留本地 $kept_local 个，相同 $identical 个，冲突 $conflicts 个，上游删除同步 $upstream_removed 个"
  if (( conflicts > 0 )); then
    warn "${label} 存在冲突，新镜像版本已保存到 ${conflicts_dir}，请上线后人工核对。"
  fi
}

additive_sync_tree() {
  local label="$1"
  local new_dir="$2"
  local host_dir="$3"
  local added=0
  local skipped=0
  local rel="" host_file="" new_file=""

  while IFS= read -r -d '' new_file; do
    rel="${new_file#$new_dir/}"
    host_file="$host_dir/$rel"

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
    warn "当前没有可用智能合并基线，${label} 将退化为"只补充缺失文件"模式。"
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

backup_existing_content_before_update() {
  if [[ "$DEPLOY_KIND" != "update" ]]; then
    return 0
  fi

  local backup_root="$YX_ROOT/backups/pre-upgrade-$(date '+%Y%m%d-%H%M%S')"
  phase "Backing up existing customer content before upgrade"
  backup_dir_if_exists "$DATA_DIR" "$backup_root" "data"
  backup_dir_if_exists "$PAGES_DIR" "$backup_root" "pages"
  backup_dir_if_exists "$CDN_ASSETS_DIR" "$backup_root" "cdn_assets"
  backup_dir_if_exists "$LEGACY_CDN_DIR" "$backup_root" "legacy_cdn"
  if [[ -f "$DATA_DIR/config.json" ]]; then
    mkdir -p "$backup_root/config"
    cp -p "$DATA_DIR/config.json" "$backup_root/config/config.json"
    info "Backed up legacy config: $backup_root/config/config.json"
  fi
}

disable_legacy_cdn_redirect_config() {
  local config_file="$DATA_DIR/config.json"
  [[ -f "$config_file" ]] || return 0

  local migration_dir="$YX_ROOT/backups/cdn-config-migration-$(date '+%Y%m%d-%H%M%S')"
  mkdir -p "$migration_dir"
  cp -p "$config_file" "$migration_dir/config.json"
  info "Backed up CDN redirect config before disabling legacy redirects: $migration_dir/config.json"

  if grep -q '"cdn_enabled"[[:space:]]*:[[:space:]]*true' "$config_file"; then
    sed -i 's/"cdn_enabled"[[:space:]]*:[[:space:]]*true/"cdn_enabled": false/g' "$config_file"
    info "Disabled legacy cdn_enabled flag; ESA should cache /cdn_assets on the main domain."
  fi
}

reset_host_content_from_image() {
  local backup_root="$1"

  phase "执行全新部署内容重置"
  if [[ -n "$backup_root" ]]; then
    info "本次会先备份旧内容，备份目录：$backup_root"
    backup_dir_if_exists "$DATA_DIR" "$backup_root" "data"
    backup_dir_if_exists "$PAGES_DIR" "$backup_root" "pages"
    backup_dir_if_exists "$CDN_ASSETS_DIR" "$backup_root" "cdn_assets"
    backup_dir_if_exists "$LEGACY_CDN_DIR" "$backup_root" "legacy_cdn"
    backup_dir_if_exists "$LEGACY_UPDATE_LOGS_DIR" "$backup_root" "legacy_update_logs"
  else
    info "当前属于首次部署，无需备份旧内容。"
  fi

  for path in \
    "$DATA_DIR" \
    "$PAGES_DIR" \
    "$CDN_ASSETS_DIR" \
    "$LEGACY_CDN_DIR" \
    "$LEGACY_UPDATE_LOGS_DIR" \
    "$DATA_BASELINE_DIR" \
    "$DATA_CONFLICTS_DIR" \
    "$PAGES_BASELINE_DIR" \
    "$PAGES_CONFLICTS_DIR" \
    "$CDN_ASSETS_BASELINE_DIR" \
    "$CDN_ASSETS_CONFLICTS_DIR"; do
    if [[ -e "$path" ]]; then
      info "正在删除旧目录：$path"
      rm -rf "$path"
      info "已删除：$path"
    else
      info "无需删除：$path 不存在"
    fi
  done

  mkdir -p "$DATA_DIR" "$PAGES_DIR" "$CDN_ASSETS_DIR"
  info "开始导入新镜像 data 目录到宿主机"
  rsync -a "$TMP_DATA_DIR/" "$DATA_DIR/"
  info "开始导入新镜像 pages 目录到宿主机"
  rsync -a "$TMP_PAGES_DIR/" "$PAGES_DIR/"
  info "开始导入新镜像 cdn_assets 目录到宿主机"
  rsync -a "$TMP_CDN_ASSETS_DIR/" "$CDN_ASSETS_DIR/"

  refresh_baseline_dir "data 目录" "$TMP_DATA_DIR" "$DATA_BASELINE_DIR"
  refresh_baseline_dir "pages 目录" "$TMP_PAGES_DIR" "$PAGES_BASELINE_DIR"
  refresh_baseline_dir "cdn_assets 目录" "$TMP_CDN_ASSETS_DIR" "$CDN_ASSETS_BASELINE_DIR"

  log_tree_state "全新部署后的 data 目录状态" "$DATA_DIR"
  log_tree_state "全新部署后的 pages 目录状态" "$PAGES_DIR"
  log_tree_state "全新部署后的 cdn_assets 目录状态" "$CDN_ASSETS_DIR"
}

reset_host_content_keep_data() {
  local backup_root="$1"

  phase "执行重置界面（保留用户数据）"
  if [[ -n "$backup_root" ]]; then
    info "本次会先备份旧内容，备份目录：$backup_root"
    backup_dir_if_exists "$PAGES_DIR" "$backup_root" "pages"
    backup_dir_if_exists "$CDN_ASSETS_DIR" "$backup_root" "cdn_assets"
    backup_dir_if_exists "$LEGACY_CDN_DIR" "$backup_root" "legacy_cdn"
    backup_dir_if_exists "$LEGACY_UPDATE_LOGS_DIR" "$backup_root" "legacy_update_logs"
  fi

  info "保留 data 目录不做改动：$DATA_DIR"
  log_tree_state "保留的 data 目录状态" "$DATA_DIR"

  for path in \
    "$PAGES_DIR" \
    "$CDN_ASSETS_DIR" \
    "$LEGACY_CDN_DIR" \
    "$LEGACY_UPDATE_LOGS_DIR" \
    "$PAGES_BASELINE_DIR" \
    "$PAGES_CONFLICTS_DIR" \
    "$CDN_ASSETS_BASELINE_DIR" \
    "$CDN_ASSETS_CONFLICTS_DIR"; do
    if [[ -e "$path" ]]; then
      info "正在删除旧目录：$path"
      rm -rf "$path"
      info "已删除：$path"
    else
      info "无需删除：$path 不存在"
    fi
  done

  mkdir -p "$PAGES_DIR" "$CDN_ASSETS_DIR"
  info "开始导入新镜像 pages 目录到宿主机"
  rsync -a "$TMP_PAGES_DIR/" "$PAGES_DIR/"
  info "开始导入新镜像 cdn_assets 目录到宿主机"
  rsync -a "$TMP_CDN_ASSETS_DIR/" "$CDN_ASSETS_DIR/"

  # data 基线必须保持为旧镜像内容：宿主机 data 本次未被改动，基线仍是
  # 其真实来源；若刷新成新镜像，下次智能合并会把上游 data 变更误判为冲突。
  refresh_baseline_dir "pages 目录" "$TMP_PAGES_DIR" "$PAGES_BASELINE_DIR"
  refresh_baseline_dir "cdn_assets 目录" "$TMP_CDN_ASSETS_DIR" "$CDN_ASSETS_BASELINE_DIR"

  log_tree_state "重置后的 pages 目录状态" "$PAGES_DIR"
  log_tree_state "重置后的 cdn_assets 目录状态" "$CDN_ASSETS_DIR"
}

pick_value() {
  local key="$1"
  local default_value="$2"
  local out_value_var="$3"
  local out_source_var="$4"
  local picked_value=""
  local picked_source=""

  picked_value="$(trim "${!key-}")"
  if [[ -n "$picked_value" ]]; then
    picked_source="当前 shell 环境变量"
  else
    picked_value="$(get_existing_env "$key")"
    if [[ -n "$picked_value" ]]; then
      picked_source="旧网站容器环境变量"
    else
      picked_value="$default_value"
      picked_source="脚本默认值"
    fi
  fi

  printf -v "$out_value_var" '%s' "$picked_value"
  printf -v "$out_source_var" '%s' "$picked_source"
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
  local value_source=""

  pick_value APP_ENV production APP_ENV_VAL value_source
  info "APP_ENV=${APP_ENV_VAL}（来源：${value_source}）"

  pick_value ADMIN_USERNAME admin ADMIN_USERNAME_VAL value_source
  info "ADMIN_USERNAME=${ADMIN_USERNAME_VAL}（来源：${value_source}）"

  HIDDEN_ADMIN_USERNAME_VAL="$(trim "${HIDDEN_ADMIN_USERNAME-}")"
  HIDDEN_ADMIN_PASSWORD_HASH_VAL="$(trim "${HIDDEN_ADMIN_PASSWORD_HASH-}")"
  HIDDEN_ADMIN_PASSWORD_VAL="$(trim "${HIDDEN_ADMIN_PASSWORD-}")"
  info "HIDDEN_ADMIN_USERNAME=${HIDDEN_ADMIN_USERNAME_VAL:-<not set>} (source: external env)"
  info "HIDDEN_ADMIN_PASSWORD_HASH=$([[ -n "$HIDDEN_ADMIN_PASSWORD_HASH_VAL" ]] && printf 'provided' || printf 'not provided') (source: external env)"
  info "HIDDEN_ADMIN_PASSWORD=$([[ -n "$HIDDEN_ADMIN_PASSWORD_VAL" ]] && printf 'provided' || printf 'not provided') (source: external env)"

  pick_value TRUST_PROXY_HEADERS true TRUST_PROXY_HEADERS_VAL value_source
  info "TRUST_PROXY_HEADERS=${TRUST_PROXY_HEADERS_VAL}（来源：${value_source}）"

  pick_value SESSION_COOKIE_SECURE true SESSION_COOKIE_SECURE_VAL value_source
  info "SESSION_COOKIE_SECURE=${SESSION_COOKIE_SECURE_VAL}（来源：${value_source}）"

  pick_value CDN_ENABLED false CDN_ENABLED_VAL value_source
  info "CDN_ENABLED=${CDN_ENABLED_VAL}（来源：${value_source}）"

  pick_value CDN_DOMAIN "" CDN_DOMAIN_VAL value_source
  CDN_ENABLED_VAL=false
  info "CDN dedicated domain redirects are deprecated; /cdn_assets is served on the main site domain for ESA caching."
  info "CDN_DOMAIN=${CDN_DOMAIN_VAL:-<未设置>}（来源：${value_source}）"

  pick_value TURNSTILE_ENABLED false TURNSTILE_ENABLED_VAL value_source
  info "TURNSTILE_ENABLED=${TURNSTILE_ENABLED_VAL}（来源：${value_source}）"

  pick_value ALLOW_WEAK_ADMIN_PASSWORDS false ALLOW_WEAK_ADMIN_PASSWORDS_VAL value_source
  info "ALLOW_WEAK_ADMIN_PASSWORDS=${ALLOW_WEAK_ADMIN_PASSWORDS_VAL}（来源：${value_source}）"

  pick_value TURNSTILE_SITE_KEY "" TURNSTILE_SITE_KEY_VAL value_source
  info "TURNSTILE_SITE_KEY=$([[ -n "$TURNSTILE_SITE_KEY_VAL" ]] && printf '已提供' || printf '未提供')（来源：${value_source}）"

  pick_value TURNSTILE_SECRET_KEY "" TURNSTILE_SECRET_KEY_VAL value_source
  info "TURNSTILE_SECRET_KEY=$([[ -n "$TURNSTILE_SECRET_KEY_VAL" ]] && printf '已提供' || printf '未提供')（来源：${value_source}）"

  pick_value ADMIN_CAPTCHA_PROVIDER "" ADMIN_CAPTCHA_PROVIDER_VAL value_source
  info "ADMIN_CAPTCHA_PROVIDER=${ADMIN_CAPTCHA_PROVIDER_VAL:-<未设置，默认 cloudflare>}（来源：${value_source}）"

  pick_value ADMIN_ESA_IDENTITY "" ADMIN_ESA_IDENTITY_VAL value_source
  info "ADMIN_ESA_IDENTITY=$([[ -n "$ADMIN_ESA_IDENTITY_VAL" ]] && printf '已提供' || printf '未提供')（来源：${value_source}）"

  pick_value ADMIN_ESA_SCENE_ID "" ADMIN_ESA_SCENE_ID_VAL value_source
  info "ADMIN_ESA_SCENE_ID=$([[ -n "$ADMIN_ESA_SCENE_ID_VAL" ]] && printf '已提供' || printf '未提供')（来源：${value_source}）"

  pick_value ADMIN_ESA_REGION "" ADMIN_ESA_REGION_VAL value_source
  info "ADMIN_ESA_REGION=${ADMIN_ESA_REGION_VAL:-<未设置，默认 cn>}（来源：${value_source}）"

  pick_value TURNSTILE_PROXY_URL "" TURNSTILE_PROXY_URL_VAL value_source
  info "TURNSTILE_PROXY_URL=$([[ -n "$TURNSTILE_PROXY_URL_VAL" ]] && printf '已提供' || printf '未提供')（来源：${value_source}）"

  pick_value TURNSTILE_PROXY_FALLBACK_ENABLED "" TURNSTILE_PROXY_FALLBACK_ENABLED_VAL value_source
  info "TURNSTILE_PROXY_FALLBACK_ENABLED=${TURNSTILE_PROXY_FALLBACK_ENABLED_VAL:-<未设置>}（来源：${value_source}）"
}

resolve_secret_key() {
  local value=""
  local source=""

  pick_value SECRET_KEY "" value source

  if [[ -n "$value" && ${#value} -lt 32 ]]; then
    warn "检测到的 SECRET_KEY 长度不足 32 位，将改为交互输入。"
    value=""
    source=""
  fi

  if [[ -n "$value" ]] && is_placeholder_secret "$value"; then
    warn "检测到 SECRET_KEY 是常见占位值，生产环境会被应用拒绝，将改为交互输入。"
    value=""
    source=""
  fi

  if [[ -z "$value" ]]; then
    prompt_confirm_secret_into value "请输入 SECRET_KEY（至少 32 位，生产环境务必固定不变）" 32
    source="交互输入"
  fi

  SECRET_KEY_VAL="$value"
  info "SECRET_KEY 已确认（来源：${source}，长度：${#SECRET_KEY_VAL}）"
}

resolve_public_base_url() {
  local value=""
  local normalized=""
  local source=""

  pick_value PUBLIC_BASE_URL "" value source
  normalized="$(normalize_public_base_url "$value")"

  if [[ -z "$normalized" ]]; then
    # 只把"本身合法"的值作为默认值回显；无效值当默认值会出现
    # "按回车永远提交同一个非法值"的死循环。
    local default_url=""
    if [[ -n "$value" ]]; then
      default_url="$(normalize_public_base_url "$value")"
    fi
    while true; do
      prompt_line_into value "请输入站点公开访问地址，例如 https://test.hnmetachip.cn" "$default_url" false
      normalized="$(normalize_public_base_url "$value")"
      if [[ -n "$normalized" ]]; then
        source="交互输入"
        break
      fi
      warn "PUBLIC_BASE_URL 格式无效，请输入带域名的 http/https 地址。"
    done
  fi

  PUBLIC_BASE_URL_VAL="$normalized"
  info "PUBLIC_BASE_URL=${PUBLIC_BASE_URL_VAL}（来源：${source}）"
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

  prompt_confirm_secret_into ADMIN_PASSWORD_VAL "请输入超级管理员初始密码（至少 6 位）" 6
  info "超级管理员初始密码已通过交互输入获取。"
}

validate_hidden_admin_runtime_values() {
  if [[ -z "${HIDDEN_ADMIN_USERNAME_VAL:-}" ]]; then
    if [[ -n "${HIDDEN_ADMIN_PASSWORD_HASH_VAL:-}" || -n "${HIDDEN_ADMIN_PASSWORD_VAL:-}" ]]; then
      die "已提供 HIDDEN_ADMIN_PASSWORD_HASH/HIDDEN_ADMIN_PASSWORD，但缺少 HIDDEN_ADMIN_USERNAME"
    fi
    return 0
  fi

  if [[ ! "$HIDDEN_ADMIN_USERNAME_VAL" =~ ^[A-Za-z0-9_.-]{3,32}$ ]]; then
    die "HIDDEN_ADMIN_USERNAME 格式不合法，仅支持 3-32 位字母、数字、下划线、点、短横线"
  fi

  if [[ "$HIDDEN_ADMIN_USERNAME_VAL" == "$ADMIN_USERNAME_VAL" ]]; then
    die "HIDDEN_ADMIN_USERNAME 不能与 ADMIN_USERNAME 相同"
  fi

  if [[ -z "${HIDDEN_ADMIN_PASSWORD_HASH_VAL:-}" && -z "${HIDDEN_ADMIN_PASSWORD_VAL:-}" ]]; then
    die "启用隐藏超级管理员时，必须提供 HIDDEN_ADMIN_PASSWORD_HASH 或 HIDDEN_ADMIN_PASSWORD"
  fi

  if [[ -n "${HIDDEN_ADMIN_PASSWORD_VAL:-}" && ${#HIDDEN_ADMIN_PASSWORD_VAL} -lt 8 ]]; then
    die "HIDDEN_ADMIN_PASSWORD 长度至少需要 8 位"
  fi
}

detect_published_host_port() {
  local container="$1"
  local line=""
  line="$(docker port "$container" 8000/tcp 2>/dev/null | grep '^127\.0\.0\.1:' | head -n 1 | awk -F: '{print $NF}')"
  if [[ -z "$line" ]]; then
    line="$(docker port "$container" 8000/tcp 2>/dev/null | head -n 1 | awk -F: '{print $NF}')"
  fi
  [[ "$line" =~ ^[0-9]+$ ]] || line=""
  printf '%s' "$line"
}

load_existing_state() {
  HAS_WEBSITE_CONTAINER=false
  HAS_LEGACY_GATEWAY_CONTAINER=false
  EXISTING_ENV_LINES=""
  EXISTING_IMAGE_REF=""

  if docker container inspect "$WEBSITE_CONTAINER" >/dev/null 2>&1; then
    HAS_WEBSITE_CONTAINER=true
    EXISTING_ENV_LINES="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$WEBSITE_CONTAINER" || true)"
    EXISTING_IMAGE_REF="$(docker inspect -f '{{.Image}}' "$WEBSITE_CONTAINER" || true)"
  fi

  if docker container inspect "$LEGACY_GATEWAY_CONTAINER" >/dev/null 2>&1; then
    HAS_LEGACY_GATEWAY_CONTAINER=true
  fi

  # 操作者若曾用非默认端口部署，升级时自动沿用，避免静默回到默认端口导致回源断开
  if [[ "$HAS_WEBSITE_CONTAINER" == "true" ]]; then
    local detected_main_port
    detected_main_port="$(detect_published_host_port "$WEBSITE_CONTAINER")"
    if [[ -z "$MAIN_PORT_EXPLICIT" && -n "$detected_main_port" && "$detected_main_port" != "$MAIN_PORT" ]]; then
      info "检测到旧网站容器端口映射为 127.0.0.1:${detected_main_port}，自动沿用（可用 MAIN_PORT 环境变量覆盖）。"
      MAIN_PORT="$detected_main_port"
    fi
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
  info "旧版 gateway 容器是否存在：$HAS_LEGACY_GATEWAY_CONTAINER"
  info "宿主机 data 文件数：$DATA_FILE_COUNT"
  info "宿主机 pages 文件数：$PAGES_FILE_COUNT"
  info "旧版宿主机 cdn_assets 文件数：$LEGACY_CDN_FILE_COUNT"
  info "旧版宿主机 update_logs 文件数：$LEGACY_UPDATE_LOGS_FILE_COUNT"

  if [[ "$HAS_WEBSITE_CONTAINER" == "true" || "$HAS_LEGACY_GATEWAY_CONTAINER" == "true" || "$HAS_HOST_CONTENT" == "true" ]]; then
    DEPLOY_KIND="update"
    info "判断结果：当前机器上已存在部署痕迹，本次按"更新部署"处理。"
  else
    DEPLOY_KIND="fresh"
    info "判断结果：当前机器上未发现部署痕迹，本次按"首次部署"处理。"
  fi

  if [[ "$DEPLOY_KIND" == "fresh" ]]; then
    DEPLOY_STRATEGY_MODE="reset"
    info "首次部署无需选择更新策略，将自动按"全新初始化导入"执行。"
    return 0
  fi

  DEPLOY_STRATEGY_MODE="$(normalize_deploy_strategy "${DEPLOY_STRATEGY:-}")"
  if [[ -n "$DEPLOY_STRATEGY_MODE" ]]; then
    info "检测到外部指定 DEPLOY_STRATEGY=${DEPLOY_STRATEGY_MODE}，本次将按指定策略执行。"
  else
    DEPLOY_STRATEGY_MODE="$(choose_update_strategy)"
  fi

  if [[ "$DEPLOY_STRATEGY_MODE" == "reset" ]]; then
    confirm_reset_action
  elif [[ "$DEPLOY_STRATEGY_MODE" == "reset-keep-data" ]]; then
    confirm_reset_keep_data_action
  fi
}

prepare_directories_and_network() {
  phase "准备目录和 Docker 网络"
  mkdir -p "$DATA_DIR" "$PAGES_DIR" "$CDN_ASSETS_DIR" "$DATA_DIR/logs"

  if docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    info "Docker 网络已存在：$NETWORK_NAME"
  else
    info "Docker 网络不存在，正在创建：$NETWORK_NAME"
    docker network create "$NETWORK_NAME" >/dev/null
    info "Docker 网络创建完成：$NETWORK_NAME"
  fi

  log_tree_state "data 目录初始化状态" "$DATA_DIR"
  log_tree_state "pages 目录初始化状态" "$PAGES_DIR"
  log_tree_state "cdn_assets 目录初始化状态" "$CDN_ASSETS_DIR"
}

pull_with_timeout() {
  local image="$1"
  local label="$2"
  info "正在拉取${label}镜像：$image"
  info "下面会显示 Docker 原生镜像拉取进度，请等待拉取完成。"
  if command -v timeout >/dev/null 2>&1; then
    timeout "${PULL_TIMEOUT:-1200}" docker pull "$image" || die "${label}镜像拉取失败或超时（${PULL_TIMEOUT:-1200} 秒限制）。请检查网络与镜像地址；境内网络建议为 Docker 配置镜像加速，或先在能访问 ghcr.io 的机器上保存/导入镜像后，用 SKIP_IMAGE_PULL=true 重跑本脚本。"
  else
    docker pull "$image" || die "${label}镜像拉取失败。请检查网络与镜像地址；也可先在本机准备好镜像后，用 SKIP_IMAGE_PULL=true 重跑本脚本。"
  fi
  success "${label}镜像拉取完成。"
}

# 重新 pull :latest 后旧镜像会变成 dangling，成功后的镜像清理会把它删掉；
# 先打 previous 标签，之后发现新版本有问题时可手动用该标签回滚。
image_repo_without_tag() {
  # 仅当镜像名末段（最后一个 / 之后）含冒号时才剥离 tag，避免误截注册表端口
  local image="$1"
  if [[ "${image##*/}" == *:* ]]; then
    printf '%s' "${image%:*}"
  else
    printf '%s' "$image"
  fi
}

preserve_previous_images() {
  if [[ -n "$EXISTING_IMAGE_REF" ]]; then
    local previous_website_tag
    previous_website_tag="$(image_repo_without_tag "$WEBSITE_IMAGE"):previous"
    if docker tag "$EXISTING_IMAGE_REF" "$previous_website_tag" >/dev/null 2>&1; then
      info "旧版网站镜像已保留为：$previous_website_tag（需要回退时可手动运行该标签）"
    else
      warn "旧版网站镜像标记失败（$EXISTING_IMAGE_REF），如需回退可能要重新拉取旧版镜像。"
    fi
  fi
}

# 记录本次实际部署的镜像版本：CI 打的 OCI 标签里带 git 提交号，
# 追加到本地历史文件，方便售后按版本定位问题。
record_deployed_image() {
  local label_name="$1"
  local image="$2"
  local revision="" created="" digest=""

  revision="$(docker image inspect "$image" --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' 2>/dev/null || true)"
  created="$(docker image inspect "$image" --format '{{ .Created }}' 2>/dev/null || true)"
  digest="$(docker image inspect "$image" --format '{{ join .RepoDigests "," }}' 2>/dev/null || true)"

  info "[${label_name}] 镜像构建时间：${created:-unknown}"
  if [[ -n "$revision" ]]; then
    info "[${label_name}] 镜像代码版本（git）：$revision"
  else
    info "[${label_name}] 镜像未携带 git 版本标签（本地构建镜像常见），以摘要为准。"
  fi
  if [[ -n "$digest" ]]; then
    info "[${label_name}] 镜像摘要：$digest"
  fi
  mkdir -p "$YX_ROOT"
  printf '%s\t%s\t%s\t%s\t%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$label_name" "$image" "${revision:-unknown}" "${digest:-unknown}" >> "$DEPLOY_RECORD_FILE" 2>/dev/null || true
}

pull_latest_images() {
  phase "拉取最新镜像"
  if bool_true "${SKIP_IMAGE_PULL:-false}"; then
    info "SKIP_IMAGE_PULL=true，跳过镜像拉取，使用本机已有镜像：$WEBSITE_IMAGE"
    preserve_previous_images
    record_deployed_image "网站" "$WEBSITE_IMAGE"
    return 0
  fi
  preserve_previous_images
  pull_with_timeout "$WEBSITE_IMAGE" "网站"
  record_deployed_image "网站" "$WEBSITE_IMAGE"
}

prepare_content_for_fresh_or_reset() {
  phase "准备首次部署 / 全新重置所需的新版本内容"
  export_image_tree "$WEBSITE_IMAGE" "$TMP_NEW_CONTAINER-data" "/app/data" "$TMP_DATA_DIR" || die "无法从新镜像导出 /app/data"
  export_image_tree "$WEBSITE_IMAGE" "$TMP_NEW_CONTAINER-pages" "/app/pages" "$TMP_PAGES_DIR" || die "无法从新镜像导出 /app/pages"
  export_image_tree "$WEBSITE_IMAGE" "$TMP_NEW_CONTAINER-cdn" "/app/cdn_assets" "$TMP_CDN_ASSETS_DIR" || die "无法从新镜像导出 /app/cdn_assets"
  log_tree_state "新镜像 data 导出结果" "$TMP_DATA_DIR"
  log_tree_state "新镜像 pages 导出结果" "$TMP_PAGES_DIR"
  log_tree_state "新镜像 cdn_assets 导出结果" "$TMP_CDN_ASSETS_DIR"

  local backup_root=""
  if [[ "$DEPLOY_KIND" == "update" && "$DEPLOY_STRATEGY_MODE" == "reset" ]]; then
    backup_root="$YX_ROOT/backups/reset-$(date '+%Y%m%d-%H%M%S')"
  fi

  reset_host_content_from_image "$backup_root"
}

prepare_content_for_smart_update() {
  sync_image_tree "data 目录" "data" "/app/data" "$DATA_DIR" "$DATA_BASELINE_DIR" "$DATA_CONFLICTS_DIR" "$TMP_DATA_DIR" "$TMP_OLD_DATA_DIR"
  sync_image_tree "pages 目录" "pages" "/app/pages" "$PAGES_DIR" "$PAGES_BASELINE_DIR" "$PAGES_CONFLICTS_DIR" "$TMP_PAGES_DIR" "$TMP_OLD_PAGES_DIR"
  sync_image_tree "cdn_assets 目录" "cdn" "/app/cdn_assets" "$CDN_ASSETS_DIR" "$CDN_ASSETS_BASELINE_DIR" "$CDN_ASSETS_CONFLICTS_DIR" "$TMP_CDN_ASSETS_DIR" "$TMP_OLD_CDN_ASSETS_DIR"
}

prepare_content_for_reset_keep_data() {
  phase "准备重置界面（保留用户数据）所需的新版本内容"
  # data 完整保留且基线不刷新，因此无需导出新镜像 data。
  export_image_tree "$WEBSITE_IMAGE" "$TMP_NEW_CONTAINER-pages" "/app/pages" "$TMP_PAGES_DIR" || die "无法从新镜像导出 /app/pages"
  export_image_tree "$WEBSITE_IMAGE" "$TMP_NEW_CONTAINER-cdn" "/app/cdn_assets" "$TMP_CDN_ASSETS_DIR" || die "无法从新镜像导出 /app/cdn_assets"
  log_tree_state "新镜像 pages 导出结果" "$TMP_PAGES_DIR"
  log_tree_state "新镜像 cdn_assets 导出结果" "$TMP_CDN_ASSETS_DIR"

  local backup_root="$YX_ROOT/backups/reset-keep-data-$(date '+%Y%m%d-%H%M%S')"
  reset_host_content_keep_data "$backup_root"
}

rollback_containers() {
  local has_old_website="$1"
  local has_old_gateway="$2"

  warn "正在尝试回滚到旧容器..."
  docker rm -f "$WEBSITE_CONTAINER" >/dev/null 2>&1 || true
  docker rm -f "$LEGACY_GATEWAY_CONTAINER" >/dev/null 2>&1 || true

  if [[ "$has_old_website" == "true" ]]; then
    docker rename "${WEBSITE_CONTAINER}-old" "$WEBSITE_CONTAINER" >/dev/null 2>&1 || true
    docker start "$WEBSITE_CONTAINER" >/dev/null 2>&1 || true
    info "已回滚网站容器到旧版本"
  fi

  if [[ "$has_old_gateway" == "true" ]]; then
    docker rename "${LEGACY_GATEWAY_CONTAINER}-old" "$LEGACY_GATEWAY_CONTAINER" >/dev/null 2>&1 || true
    docker start "$LEGACY_GATEWAY_CONTAINER" >/dev/null 2>&1 || true
    info "已回滚旧版 gateway 容器"
  fi

}

recreate_containers() {
  phase "重建容器"

  # 停止并重命名旧容器（保留以备回滚）
  local has_old_website=false
  local has_old_gateway=false

  if docker container inspect "$WEBSITE_CONTAINER" >/dev/null 2>&1; then
    info "正在停止旧网站容器并重命名为 ${WEBSITE_CONTAINER}-old"
    docker stop "$WEBSITE_CONTAINER" >/dev/null 2>&1 || true
    docker rename "$WEBSITE_CONTAINER" "${WEBSITE_CONTAINER}-old" >/dev/null 2>&1 || true
    has_old_website=true
  fi

  if docker container inspect "$LEGACY_GATEWAY_CONTAINER" >/dev/null 2>&1; then
    info "检测到旧版 gateway 容器，正在停止并重命名为 ${LEGACY_GATEWAY_CONTAINER}-old（仅用于失败回滚）"
    docker stop "$LEGACY_GATEWAY_CONTAINER" >/dev/null 2>&1 || true
    docker rename "$LEGACY_GATEWAY_CONTAINER" "${LEGACY_GATEWAY_CONTAINER}-old" >/dev/null 2>&1 || true
    has_old_gateway=true
  fi

  website_cmd=(
    docker run -d
    --name "$WEBSITE_CONTAINER"
    --restart unless-stopped
    --network "$NETWORK_NAME"
    --network-alias "$WEBSITE_CONTAINER"
    -p "127.0.0.1:${MAIN_PORT}:8000"
    -e "APP_ENV=$APP_ENV_VAL"
    -e "SECRET_KEY=$SECRET_KEY_VAL"
    -e "PUBLIC_BASE_URL=$PUBLIC_BASE_URL_VAL"
    -e "TRUST_PROXY_HEADERS=$TRUST_PROXY_HEADERS_VAL"
    -e "SESSION_COOKIE_SECURE=$SESSION_COOKIE_SECURE_VAL"
    -e "ADMIN_USERNAME=$ADMIN_USERNAME_VAL"
    -e "CDN_ENABLED=$CDN_ENABLED_VAL"
    -e "TURNSTILE_ENABLED=$TURNSTILE_ENABLED_VAL"
    -e "ALLOW_WEAK_ADMIN_PASSWORDS=$ALLOW_WEAK_ADMIN_PASSWORDS_VAL"
    -e "DOCKER_CONTAINER_1_NAME=$WEBSITE_CONTAINER"
    -e "DOCKER_LOG_FALLBACK_APP_FILES=/app/data/logs/gunicorn-error.log,/app/data/logs/gunicorn-access.log,/app/data/logs/app.log"
    -v "$DATA_DIR:/app/data"
    -v "$PAGES_DIR:/app/pages"
    -v "$CDN_ASSETS_DIR:/app/cdn_assets"
  )

  if [[ -n "$ADMIN_PASSWORD_HASH_VAL" ]]; then
    website_cmd+=( -e "ADMIN_PASSWORD_HASH=$ADMIN_PASSWORD_HASH_VAL" )
  fi
  if [[ -n "$ADMIN_PASSWORD_VAL" ]]; then
    website_cmd+=( -e "ADMIN_PASSWORD=$ADMIN_PASSWORD_VAL" )
  fi
  if [[ -n "$HIDDEN_ADMIN_USERNAME_VAL" ]]; then
    website_cmd+=( -e "HIDDEN_ADMIN_USERNAME=$HIDDEN_ADMIN_USERNAME_VAL" )
  fi
  if [[ -n "$HIDDEN_ADMIN_PASSWORD_HASH_VAL" ]]; then
    website_cmd+=( -e "HIDDEN_ADMIN_PASSWORD_HASH=$HIDDEN_ADMIN_PASSWORD_HASH_VAL" )
  fi
  if [[ -n "$HIDDEN_ADMIN_PASSWORD_VAL" ]]; then
    website_cmd+=( -e "HIDDEN_ADMIN_PASSWORD=$HIDDEN_ADMIN_PASSWORD_VAL" )
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
  if [[ -n "$ADMIN_CAPTCHA_PROVIDER_VAL" ]]; then
    website_cmd+=( -e "ADMIN_CAPTCHA_PROVIDER=$ADMIN_CAPTCHA_PROVIDER_VAL" )
  fi
  if [[ -n "$ADMIN_ESA_IDENTITY_VAL" ]]; then
    website_cmd+=( -e "ADMIN_ESA_IDENTITY=$ADMIN_ESA_IDENTITY_VAL" )
  fi
  if [[ -n "$ADMIN_ESA_SCENE_ID_VAL" ]]; then
    website_cmd+=( -e "ADMIN_ESA_SCENE_ID=$ADMIN_ESA_SCENE_ID_VAL" )
  fi
  if [[ -n "$ADMIN_ESA_REGION_VAL" ]]; then
    website_cmd+=( -e "ADMIN_ESA_REGION=$ADMIN_ESA_REGION_VAL" )
  fi
  if [[ -n "$TURNSTILE_PROXY_URL_VAL" ]]; then
    website_cmd+=( -e "TURNSTILE_PROXY_URL=$TURNSTILE_PROXY_URL_VAL" )
  fi
  if [[ -n "$TURNSTILE_PROXY_FALLBACK_ENABLED_VAL" ]]; then
    website_cmd+=( -e "TURNSTILE_PROXY_FALLBACK_ENABLED=$TURNSTILE_PROXY_FALLBACK_ENABLED_VAL" )
  fi
  # 继承旧容器中脚本未托管的应用环境变量（值可能含空格，保持数组展开）
  if (( ${#CARRIED_WEBSITE_ENV[@]} > 0 )); then
    website_cmd+=( "${CARRIED_WEBSITE_ENV[@]}" )
  fi

  website_cmd+=( "$WEBSITE_IMAGE" )

  info "正在启动网站容器：$WEBSITE_CONTAINER"
  info "网站容器网络：${NETWORK_NAME}，网络别名：${WEBSITE_CONTAINER}"
  info "网站容器挂载：$DATA_DIR -> /app/data"
  info "网站容器挂载：$PAGES_DIR -> /app/pages"
  info "网站容器挂载：$CDN_ASSETS_DIR -> /app/cdn_assets"
  info "网站日志目录：$DATA_DIR/logs"

  set +e
  WEBSITE_CONTAINER_ID="$("${website_cmd[@]}" 2>&1)"
  local ws_exit=$?
  set -e

  if (( ws_exit != 0 )); then
    warn "新网站容器启动失败（退出码：$ws_exit）：$WEBSITE_CONTAINER_ID"
    rollback_containers "$has_old_website" "$has_old_gateway"
    die "新网站容器启动失败，已回滚到旧版本。请检查镜像和配置。"
  fi
  success "网站容器启动成功，容器 ID：${WEBSITE_CONTAINER_ID:0:12}"

  # 同时连接 bridge 网络，确保端口映射和域名访问正常
  if ! docker network connect bridge "$WEBSITE_CONTAINER" 2>/dev/null; then
    info "网站容器已在 bridge 网络中，跳过。"
  else
    info "已将网站容器连接到 bridge 网络。"
  fi

  info "单域名 ESA 部署已取消 gateway 容器；本次只启动网站容器。"
  info "等待容器初始化（3 秒）..."
  sleep 3

  # 验证新容器是否稳定运行
  local rollback_needed=false
  for c in "$WEBSITE_CONTAINER"; do
    if ! docker ps --filter "name=^/${c}$" --format '{{.Names}}' | grep -qx "$c"; then
      warn "容器 '$c' 启动后未能稳定运行。最近日志："
      docker logs --tail 20 "$c" 2>&1 || true
      rollback_needed=true
    fi
  done

  if [[ "$rollback_needed" == "true" ]]; then
    warn "新容器未能稳定运行，正在回滚到旧版本..."
    docker rm -f "$WEBSITE_CONTAINER" >/dev/null 2>&1 || true
    rollback_containers "$has_old_website" "$has_old_gateway"
    die "新容器启动后崩溃，已回滚到旧版本。请查看上方日志排查原因。"
  fi

  success "新容器已通过稳定性验证。"

  # 新容器正常运行，清理旧容器
  if [[ "$has_old_website" == "true" ]]; then
    docker rm -f "${WEBSITE_CONTAINER}-old" >/dev/null 2>&1 || true
    info "已清理旧网站容器"
  fi
  if [[ "$has_old_gateway" == "true" ]]; then
    docker rm -f "${LEGACY_GATEWAY_CONTAINER}-old" >/dev/null 2>&1 || true
    info "已清理旧版 gateway 容器"
  fi
}

verify_containers() {
  phase "验证容器运行状态"
  for c in "$WEBSITE_CONTAINER"; do
    if ! docker ps --filter "name=^/${c}$" --format '{{.Names}}' | grep -qx "$c"; then
      die "容器 '$c' 未正常运行，请执行 docker logs $c 查看原因。"
    else
      info "容器运行正常：$c"
      info "容器详情摘要：$(docker ps --filter "name=^/${c}$" --format '{{.Names}} | {{.Image}} | {{.Status}}')"
    fi
  done

  if command -v curl >/dev/null 2>&1; then
    info "正在验证 HTTP 服务可用性..."
    local http_ok=false
    for _ in $(seq 1 15); do
      if curl -sf -o /dev/null --max-time 3 "http://127.0.0.1:${MAIN_PORT}/"; then
        http_ok=true
        break
      fi
      sleep 1
    done
    if [[ "$http_ok" == "true" ]]; then
      success "HTTP 服务验证通过：http://127.0.0.1:${MAIN_PORT}/"
    else
      warn "HTTP 服务在 15 秒内未就绪，容器进程正在运行但服务可能仍在启动中，请手动验证。"
    fi

    # 首页 200 不代表后台与新接口正常，补充两项轻量验证（只警告不阻断）
    if curl -sf -o /dev/null --max-time 3 "http://127.0.0.1:${MAIN_PORT}/api/nav-labels"; then
      success "公开导航接口验证通过：/api/nav-labels"
    else
      warn "公开导航接口 /api/nav-labels 暂未通过验证，请上线后检查后台导航设置。"
    fi
    if curl -sf -o /dev/null --max-time 3 "http://127.0.0.1:${MAIN_PORT}/admin"; then
      success "后台入口验证通过：/admin"
    else
      warn "后台入口 /admin 暂未通过验证，请上线后手动检查后台登录。"
    fi

  else
    info "未检测到 curl，跳过 HTTP 可用性验证。"
  fi
}

cleanup_old_images() {
  if bool_true "$CLEAN_OLD_IMAGES"; then
    phase "清理无用旧镜像"
    docker image prune -f >/dev/null || warn "执行 docker image prune 失败，可稍后手动清理。"
    success "无用旧镜像清理完成。"
  else
    phase "跳过旧镜像清理"
    info "CLEAN_OLD_IMAGES=$CLEAN_OLD_IMAGES"
  fi
}

cleanup() {
  docker rm -f \
    "${TMP_NEW_CONTAINER}-data" \
    "${TMP_NEW_CONTAINER}-pages" \
    "${TMP_NEW_CONTAINER}-cdn" \
    "${TMP_OLD_CONTAINER}-data" \
    "${TMP_OLD_CONTAINER}-pages" \
    "${TMP_OLD_CONTAINER}-cdn" >/dev/null 2>&1 || true
  rm -rf "$TMP_DATA_DIR" "$TMP_OLD_DATA_DIR" "$TMP_PAGES_DIR" "$TMP_OLD_PAGES_DIR" "$TMP_CDN_ASSETS_DIR" "$TMP_OLD_CDN_ASSETS_DIR"
}

show_help() {
  cat <<'USAGE'
用法：
  bash tools/dockerrun_upgrade.sh

推荐用途：
  这是网站 Docker 部署/升级的首选脚本。
  它会自动识别当前机器是"首次部署"还是"更新部署"，并在更新时让你选择：
  1. 智能合并更新
  2. 全新部署重置
  3. 重置界面，保留用户数据

可选环境变量：
  YX_ROOT=/root/yxwebsite
  NETWORK_NAME=yx-net
  WEBSITE_CONTAINER=yx-website
  WEBSITE_IMAGE=ghcr.io/zhizinan1997/yx_website:latest
  MAIN_PORT=2026                    # 未指定时自动沿用旧容器的端口映射
  CLEAN_OLD_IMAGES=true
  SKIP_IMAGE_PULL=true|false
  DEPLOY_STRATEGY=smart|reset|reset-keep-data
  ALLOW_WEAK_ADMIN_PASSWORDS=true|false
  NO_COLOR=1                # 关闭彩色终端输出
  HIDDEN_ADMIN_USERNAME=shadow_root
  HIDDEN_ADMIN_PASSWORD_HASH=...
  HIDDEN_ADMIN_PASSWORD=...
  ADMIN_CAPTCHA_PROVIDER=cloudflare|aliyun_esa   # v4.7.0 后台验证码
  ADMIN_ESA_IDENTITY=...
  ADMIN_ESA_SCENE_ID=...
  ADMIN_ESA_REGION=cn
  TURNSTILE_PROXY_URL=...
  TURNSTILE_PROXY_FALLBACK_ENABLED=true|false

交互说明：
  - 首次部署：脚本会自动导入新镜像里的 data/pages 内容，并要求输入 SECRET_KEY、PUBLIC_BASE_URL；如果还没有 admin_users.json，也会要求输入管理员初始密码。
  - 更新部署：脚本会先让你选择"智能合并更新"、"全新部署重置"或"重置界面，保留用户数据"。
  - 如果旧容器仍存在，脚本会优先复用旧容器中的 SECRET_KEY、PUBLIC_BASE_URL 等环境变量。
  - 脚本未托管的应用环境变量（SMTP、CHATBOT、PRODUCT_AI、PASSKEY、INDEXNOW、BAIDU_PUSH_TOKEN 等）会自动从旧容器继承到新容器；同名 shell 环境变量优先。继承只记录变量名，不回显值。
  - 新架构只启动网站容器；如果检测到旧版 yx-gateway 容器，会在升级成功后自动清理，失败时才临时回滚。
  - 如果缺少这些环境变量，脚本会直接在终端里提示输入。
  - 如确需允许首次初始化时使用弱密码，可显式传入 ALLOW_WEAK_ADMIN_PASSWORDS=true。

版本与回滚：
  - 拉取新镜像前，旧版镜像会自动保留为 <镜像名>:previous 标签，需要回退时可手动运行该标签。
  - 本次部署的 git 提交号与镜像摘要会追加记录到 $YX_ROOT/.deploy-history.log。
  - data 中的运行时文件（app.log、image_seo_*、site_analytics_*、登录日志等）不参与智能合并，宿主机版本始终保留。

风险说明：
  - "智能合并更新"会尽量保留宿主机已修改内容，但冲突文件仍可能需要人工核对。
  - "全新部署重置"会先备份再清空宿主机 data/pages 和旧版残留目录，再导入新镜像内容，客户数据和客户改动都会被替换。
  - "重置界面，保留用户数据"会先备份再清空 pages/cdn_assets，从新镜像重新导入，但 data 目录完整保留。
USAGE
}

# 默认值
YX_ROOT="${YX_ROOT:-/root/yxwebsite}"
NETWORK_NAME="${NETWORK_NAME:-yx-net}"
WEBSITE_CONTAINER="${WEBSITE_CONTAINER:-yx-website}"
# v4.1.0 及更早部署可能还保留 yx-gateway。新版本不再启动它，
# 这里只保留旧容器名称用于升级成功后的清理和失败回滚。
LEGACY_GATEWAY_CONTAINER="${LEGACY_GATEWAY_CONTAINER:-${GATEWAY_CONTAINER:-yx-gateway}}"
WEBSITE_IMAGE="${WEBSITE_IMAGE:-ghcr.io/zhizinan1997/yx_website:latest}"
# 端口先记录是否被显式指定：未指定时会在 load_existing_state 中自动沿用旧容器映射
MAIN_PORT_EXPLICIT="${MAIN_PORT:-}"
MAIN_PORT="${MAIN_PORT:-2026}"
CLEAN_OLD_IMAGES="${CLEAN_OLD_IMAGES:-true}"
DEPLOY_RECORD_FILE="$YX_ROOT/.deploy-history.log"

DATA_DIR="$YX_ROOT/data"
PAGES_DIR="$YX_ROOT/pages"
CDN_ASSETS_DIR="$YX_ROOT/cdn_assets"
LEGACY_UPDATE_LOGS_DIR="$YX_ROOT/update_logs"
LEGACY_CDN_DIR="$YX_ROOT/cdn"
DATA_BASELINE_DIR="$YX_ROOT/.data-image-baseline"
PAGES_BASELINE_DIR="$YX_ROOT/.pages-image-baseline"
CDN_ASSETS_BASELINE_DIR="$YX_ROOT/.cdn-assets-image-baseline"
DATA_CONFLICTS_DIR="$YX_ROOT/.data-merge-conflicts"
PAGES_CONFLICTS_DIR="$YX_ROOT/.pages-merge-conflicts"
CDN_ASSETS_CONFLICTS_DIR="$YX_ROOT/.cdn-assets-merge-conflicts"
TMP_DATA_DIR="$YX_ROOT/.tmp-data"
TMP_OLD_DATA_DIR="$YX_ROOT/.tmp-data-old"
TMP_PAGES_DIR="$YX_ROOT/.tmp-pages"
TMP_OLD_PAGES_DIR="$YX_ROOT/.tmp-pages-old"
TMP_CDN_ASSETS_DIR="$YX_ROOT/.tmp-cdn-assets"
TMP_OLD_CDN_ASSETS_DIR="$YX_ROOT/.tmp-cdn-assets-old"
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

# 防止多实例并发执行
mkdir -p "$YX_ROOT"
LOCKFILE="$YX_ROOT/.deploy.lock"
if command -v flock >/dev/null 2>&1; then
  exec 200>"$LOCKFILE"
  flock -n 200 || die "另一个部署实例正在运行中（锁文件：$LOCKFILE），请等待其完成或手动解除。"
  info "已获取部署锁：$LOCKFILE"
else
  warn "未找到 flock 命令，跳过并发执行保护。请确保不要同时运行多个部署实例。"
fi

phase "开始执行站点部署脚本"
info "脚本目标目录：$YX_ROOT"
info "网站镜像：$WEBSITE_IMAGE"
info "主站端口：$MAIN_PORT"
info "CDN 专用入口已废弃；/cdn_assets 会走主站端口并交给 ESA 缓存。"

load_existing_state
determine_deploy_kind_and_strategy
backup_existing_content_before_update
resolve_basic_runtime_values
resolve_secret_key
resolve_public_base_url
resolve_carried_env
prepare_directories_and_network
pull_latest_images

if [[ "$DEPLOY_KIND" == "fresh" || "$DEPLOY_STRATEGY_MODE" == "reset" ]]; then
  prepare_content_for_fresh_or_reset
elif [[ "$DEPLOY_STRATEGY_MODE" == "reset-keep-data" ]]; then
  prepare_content_for_reset_keep_data
else
  prepare_content_for_smart_update
fi

disable_legacy_cdn_redirect_config
resolve_admin_bootstrap_if_needed
validate_hidden_admin_runtime_values

phase "修复挂载目录权限"
chmod -R a+rX "$DATA_DIR" "$PAGES_DIR" "$CDN_ASSETS_DIR" 2>/dev/null || warn "部分文件权限修复失败，运行时可能出现权限问题，请检查目录所有者和权限。"
# v4.7.0 应用端已把密钥/凭据文件收紧为仅属主可读；上面的 a+rX 会重新放开，
# 必须再收紧，否则 config.json（含 SMTP 凭据与口令哈希）等在宿主机上全局可读。
for secret_file in \
  "$DATA_DIR/.flask_secret_key" \
  "$DATA_DIR/config.json" \
  "$DATA_DIR/admin_users.json" \
  "$DATA_DIR/admin_login_attempts.json" \
  "$DATA_DIR/admin_login_logs.json"; do
  if [[ -f "$secret_file" ]]; then
    chmod 600 "$secret_file" 2>/dev/null || warn "敏感文件权限收紧失败：$secret_file"
  fi
done
for pii_dir in "$DATA_DIR/messages" "$DATA_DIR/resumes"; do
  if [[ -d "$pii_dir" ]]; then
    chmod 700 "$pii_dir" 2>/dev/null || true
    find "$pii_dir" -type f -exec chmod 600 {} + 2>/dev/null || true
  fi
done
info "挂载目录权限检查完成。"

recreate_containers
verify_containers
cleanup_old_images

phase "部署完成"
success "部署流程执行完成。"
info "部署类型：$DEPLOY_KIND"
info "本次部署的镜像版本（git 提交/摘要）已记录：$DEPLOY_RECORD_FILE"
if [[ "$DEPLOY_KIND" == "update" ]]; then
  info "本次更新策略：$DEPLOY_STRATEGY_MODE"
fi
success "主站入口：http://127.0.0.1:${MAIN_PORT}"
success "CDN 素材入口已合并到主站：/cdn_assets/"
if has_regular_files "$DATA_CONFLICTS_DIR"; then
  warn "检测到 data 合并冲突，请检查：$DATA_CONFLICTS_DIR"
fi
if has_regular_files "$PAGES_CONFLICTS_DIR"; then
  warn "检测到 pages 合并冲突，请检查：$PAGES_CONFLICTS_DIR"
fi
if has_regular_files "$CDN_ASSETS_CONFLICTS_DIR"; then
  warn "检测到 cdn_assets 合并冲突，请检查：$CDN_ASSETS_CONFLICTS_DIR"
fi
