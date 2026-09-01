#!/usr/bin/env bash
# dockerrun_upgrade.sh 纯函数级测试。
# 从部署脚本中按函数名提取定义后逐项断言，不执行主流程、不依赖 docker。
# 运行：bash tests/test_dockerrun_upgrade.sh
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$SCRIPT_DIR/../tools/dockerrun_upgrade.sh"

if [[ ! -f "$SRC" ]]; then
  echo "FAIL: 找不到部署脚本：$SRC" >&2
  exit 1
fi

extract_fn() {
  local fn="$1"
  awk -v fn="$fn" '
    $0 ~ "^"fn"\\(\\) \\{$" { found = 1 }
    found { print }
    found && $0 == "}" { exit }
  ' "$SRC"
}

PASS_COUNT=0
FAIL_COUNT=0

assert_eq() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$expected" == "$actual" ]]; then
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf 'FAIL: %s\n  期望: [%s]\n  实际: [%s]\n' "$desc" "$expected" "$actual"
  fi
}

assert_rc() {
  local desc="$1" expected_rc="$2"
  shift 2
  local actual_rc=0
  "$@" >/dev/null 2>&1 || actual_rc=$?
  if [[ "$actual_rc" == "$expected_rc" ]]; then
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf 'FAIL: %s\n  期望退出码: %s\n  实际退出码: %s\n' "$desc" "$expected_rc" "$actual_rc"
  fi
}

assert_true() {
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf 'FAIL: %s（条件应为真）\n' "$desc"
  fi
}

assert_false() {
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    FAIL_COUNT=$((FAIL_COUNT + 1))
    printf 'FAIL: %s（条件应为假）\n' "$desc"
  else
    PASS_COUNT=$((PASS_COUNT + 1))
  fi
}

# ---- 提取被测函数；die/info 用桩替换以隔离主流程依赖 ----
eval "$(extract_fn trim)"
eval "$(extract_fn bool_true)"
eval "$(extract_fn normalize_public_base_url)"
eval "$(extract_fn normalize_deploy_strategy)"
eval "$(extract_fn is_placeholder_secret)"
eval "$(extract_fn is_system_env_key)"
eval "$(extract_fn is_runtime_merge_excluded)"
eval "$(extract_fn image_repo_without_tag)"
eval "$(extract_fn collect_carried_env_for)"
die() { echo "die: $*" >&2; exit 1; }
info() { :; }
WEBSITE_MANAGED_ENV_KEYS="$(grep -E '^WEBSITE_MANAGED_ENV_KEYS=' "$SRC" | head -n 1 | sed -e 's/^WEBSITE_MANAGED_ENV_KEYS=//' -e 's/^"//' -e 's/"$//')"
CHECK_MANAGED_ENV_KEYS="$(grep -E '^CHECK_MANAGED_ENV_KEYS=' "$SRC" | head -n 1 | sed -e 's/^CHECK_MANAGED_ENV_KEYS=//' -e 's/^"//' -e 's/"$//')"

managed_keys_contains() {
  local list="$1" key="$2"
  [[ " $list " == *" $key "* ]]
}

carried_env_contains() {
  local needle="$1"
  shift
  local item
  for item in "$@"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}

# 非法策略应触发 die：子 shell 内重定义 die 并返回专用退出码
deploy_strategy_dies() {
  (
    die() { exit 9; }
    normalize_deploy_strategy "$1" >/dev/null 2>&1
  )
}

# ---- trim ----
assert_eq "trim 去除首尾空白" "a b" "$(trim '   a b   ')"
assert_eq "trim 去除行尾 CR" "a" "$(trim $'a\r')"

# ---- bool_true ----
assert_rc "bool_true 接受 true" 0 bool_true true
assert_rc "bool_true 接受 1" 0 bool_true 1
assert_rc "bool_true 接受 YES" 0 bool_true YES
assert_rc "bool_true 拒绝 false" 1 bool_true false
assert_rc "bool_true 拒绝空值" 1 bool_true ""

# ---- normalize_public_base_url ----
assert_eq "URL 规范化去尾斜杠" "https://www.hnmetachip.cn" "$(normalize_public_base_url 'https://www.hnmetachip.cn/')"
assert_eq "URL 无协议时补 https" "https://www.hnmetachip.cn" "$(normalize_public_base_url 'www.hnmetachip.cn')"
assert_eq "URL 带端口保留" "http://test.hnmetachip.cn:8443" "$(normalize_public_base_url 'http://test.hnmetachip.cn:8443')"
assert_eq "URL 空值返回空" "" "$(normalize_public_base_url '')"
assert_eq "URL 非法值返回空" "" "$(normalize_public_base_url 'not a url')"

# ---- normalize_deploy_strategy ----
assert_eq "策略 smart" "smart" "$(normalize_deploy_strategy smart)"
assert_eq "策略 1 映射 smart" "smart" "$(normalize_deploy_strategy 1)"
assert_eq "策略 2 映射 reset" "reset" "$(normalize_deploy_strategy 2)"
assert_eq "策略 3 映射 reset-keep-data" "reset-keep-data" "$(normalize_deploy_strategy 3)"
assert_eq "策略 keep-data 别名" "reset-keep-data" "$(normalize_deploy_strategy keep-data)"
assert_eq "策略空值返回空" "" "$(normalize_deploy_strategy '')"
assert_rc "策略非法值报错退出" 9 deploy_strategy_dies bogus

# ---- is_placeholder_secret ----
assert_rc "占位密钥识别 change-me" 0 is_placeholder_secret 'change-me-in-production-1234567890abcdef'
assert_rc "占位密钥识别 replace-with" 0 is_placeholder_secret 'Replace-With-A-Real-Key-1234567890'
assert_rc "占位密钥识别 placeholder" 0 is_placeholder_secret 'some-placeholder-value-1234567890'
assert_rc "正常随机密钥不误报" 1 is_placeholder_secret 'Ab3xK9mP2vQ7wL5tR8yU1zC4nF6hJ0dG'

# ---- is_system_env_key ----
assert_true "PATH 属于系统变量" is_system_env_key PATH
assert_true "PYTHON_VERSION 属于系统变量" is_system_env_key PYTHON_VERSION
assert_true "WERKZEUG_RUN_MAIN 属于系统变量" is_system_env_key WERKZEUG_RUN_MAIN
assert_false "SMTP_HOST 不是系统变量" is_system_env_key SMTP_HOST
assert_false "INDEXNOW_KEY 不是系统变量" is_system_env_key INDEXNOW_KEY

# ---- 托管变量清单 ----
assert_true "验证码变量已纳入网站托管清单" managed_keys_contains "$WEBSITE_MANAGED_ENV_KEYS" ADMIN_CAPTCHA_PROVIDER
assert_true "ESA 变量已纳入网站托管清单" managed_keys_contains "$WEBSITE_MANAGED_ENV_KEYS" ADMIN_ESA_SCENE_ID
assert_true "TURNSTILE 代理变量已纳入网站托管清单" managed_keys_contains "$WEBSITE_MANAGED_ENV_KEYS" TURNSTILE_PROXY_URL
assert_true "CHECK_SECRET_KEY 纳入监测站托管清单" managed_keys_contains "$CHECK_MANAGED_ENV_KEYS" CHECK_SECRET_KEY

# ---- is_runtime_merge_excluded ----
assert_true "app.log 排除合并" is_runtime_merge_excluded app.log
assert_true "logs/ 下日志排除合并" is_runtime_merge_excluded logs/gunicorn-access.log
assert_true "图片 SEO 报告排除合并" is_runtime_merge_excluded image_seo_scan_report.json
assert_true "站点分析事件流排除合并" is_runtime_merge_excluded site_analytics_events.jsonl
assert_true "密钥文件排除合并" is_runtime_merge_excluded .flask_secret_key
assert_true "config.json 排除合并" is_runtime_merge_excluded config.json
assert_true "限流存储排除合并" is_runtime_merge_excluded rate_limits.json
assert_false "产品设置不排除（需三方合并）" is_runtime_merge_excluded product_settings.json
assert_false "导航标签不排除（需三方合并）" is_runtime_merge_excluded nav_labels.json
assert_false "普通页面不排除" is_runtime_merge_excluded css/foo.css

# ---- image_repo_without_tag ----
assert_eq "镜像名剥离 tag" "ghcr.io/zhizinan1997/yx_website" "$(image_repo_without_tag 'ghcr.io/zhizinan1997/yx_website:latest')"
assert_eq "无 tag 镜像名原样保留" "ghcr.io/zhizinan1997/yx_website" "$(image_repo_without_tag 'ghcr.io/zhizinan1997/yx_website')"
assert_eq "带注册表端口时仅剥离 tag" "localhost:5000/yx_website" "$(image_repo_without_tag 'localhost:5000/yx_website:latest')"
assert_eq "带注册表端口且无 tag 时不误截" "localhost:5000/yx_website" "$(image_repo_without_tag 'localhost:5000/yx_website')"

# ---- collect_carried_env_for ----
CARRIED_WEBSITE_ENV=()
CARRIED_CHECK_ENV=()
collect_carried_env_for $'SMTP_HOST=smtp.163.com\nCHATBOT_API_KEY=sk-abc=def\nPATH=/usr/bin\nSECRET_KEY=managed-key\nBAD-NAME=x\nNOEQUALS\nEMPTY=\n' "$WEBSITE_MANAGED_ENV_KEYS" "website"
assert_eq "继承变量条数（SMTP_HOST + CHATBOT_API_KEY）" "4" "${#CARRIED_WEBSITE_ENV[@]}"
assert_true "SMTP_HOST 被继承" carried_env_contains "SMTP_HOST=smtp.163.com" "${CARRIED_WEBSITE_ENV[@]}"
assert_true "含等号的值完整保留" carried_env_contains "CHATBOT_API_KEY=sk-abc=def" "${CARRIED_WEBSITE_ENV[@]}"
assert_false "PATH 不被继承" carried_env_contains "PATH=/usr/bin" "${CARRIED_WEBSITE_ENV[@]}"
assert_false "托管变量 SECRET_KEY 不被继承" carried_env_contains "SECRET_KEY=managed-key" "${CARRIED_WEBSITE_ENV[@]}"
assert_false "非法变量名不被继承" carried_env_contains "BAD-NAME=x" "${CARRIED_WEBSITE_ENV[@]}"

INDEXNOW_KEY=shell-override collect_carried_env_for $'INDEXNOW_KEY=old-container-value' "$WEBSITE_MANAGED_ENV_KEYS" "website"
assert_true "同名 shell 环境变量优先于旧容器值" carried_env_contains "INDEXNOW_KEY=shell-override" "${CARRIED_WEBSITE_ENV[@]}"

CARRIED_CHECK_ENV=()
collect_carried_env_for $'CHECK_SCHEDULER_ENABLED=true\nCHECK_SECRET_KEY=managed\nHOME=/root\n' "$CHECK_MANAGED_ENV_KEYS" "check"
assert_true "监测站自定义变量被继承" carried_env_contains "CHECK_SCHEDULER_ENABLED=true" "${CARRIED_CHECK_ENV[@]}"
assert_false "监测站托管变量不被继承" carried_env_contains "CHECK_SECRET_KEY=managed" "${CARRIED_CHECK_ENV[@]}"
assert_false "监测站系统变量不被继承" carried_env_contains "HOME=/root" "${CARRIED_CHECK_ENV[@]}"

# ---- 汇总 ----
printf '通过 %s 项，失败 %s 项\n' "$PASS_COUNT" "$FAIL_COUNT"
if (( FAIL_COUNT > 0 )); then
  exit 1
fi
exit 0
