#!/usr/bin/env bash
#
# YX Website 本地启动脚本
# 用法：在终端执行  ./start.sh   （或  bash start.sh）
# 启动后访问 http://localhost:8000 ，后台 http://localhost:8000/admin
#
set -e

# 切换到脚本所在目录，保证相对路径正确
cd "$(dirname "$0")"

# 选择 python 命令
PY=python3
command -v $PY >/dev/null 2>&1 || PY=python

# 首次运行时创建虚拟环境，避免污染系统 Python
if [ ! -d ".venv" ]; then
  echo "==> 创建虚拟环境 .venv"
  $PY -m venv .venv
fi

# 激活虚拟环境
# shellcheck disable=SC1091
source .venv/bin/activate

# 安装/更新依赖（已安装会很快跳过）
# 使用国内镜像源加速；--trusted-host 跳过本机缺失 CA 根证书导致的 SSL 校验失败（本地开发可接受）
PIP_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
PIP_HOST="pypi.tuna.tsinghua.edu.cn"
echo "==> 安装依赖 (requirements.txt)"
pip install -q -i "$PIP_MIRROR" --trusted-host "$PIP_HOST" -r requirements.txt

echo "=================================================="
echo " YX Website 正在以开发模式启动"
echo " 首页 : http://localhost:8000"
echo " 后台 : http://localhost:8000/admin   (默认 admin / admin123)"
echo " 按 Ctrl+C 停止"
echo "=================================================="

# 以开发模式启动（server.py 内部固定监听 0.0.0.0:8000）
exec python server.py
