#!/bin/bash
# 麦轮底盘控制服务器部署脚本
# 此脚本用于将底盘服务器程序部署到开发板

set -e

# 配置
BOARD_USER="HwHiAiUser"
BOARD_HOST="192.168.0.155"
BOARD_DIR="/home/HwHiAiUser"
REALBASE_LOCAL="/home/dora/RoboOs/LekiwiTest/RealBase"
SERVER_LOCAL="/tmp/base_server.py"

echo "=========================================="
echo "麦轮底盘控制服务器部署脚本"
echo "=========================================="
echo ""

# 1. 检查本地文件
echo "[1/5] 检查本地文件..."
if [ ! -d "$REALBASE_LOCAL" ]; then
    echo "错误: RealBase 目录不存在: $REALBASE_LOCAL"
    exit 1
fi
if [ ! -f "$SERVER_LOCAL" ]; then
    echo "错误: 服务器程序不存在: $SERVER_LOCAL"
    exit 1
fi
echo "✓ 本地文件检查完成"
echo ""

# 2. 复制 RealBase 到开发板
echo "[2/5] 复制 RealBase 目录到开发板..."
echo "  这可能需要几分钟..."
scp -r "$REALBASE_LOCAL" ${BOARD_USER}@${BOARD_HOST}:${BOARD_DIR}/
echo "✓ RealBase 目录已复制"
echo ""

# 3. 复制服务器程序到开发板
echo "[3/5] 复制服务器程序到开发板..."
scp "$SERVER_LOCAL" ${BOARD_USER}@${BOARD_HOST}:${BOARD_DIR}/base_server.py
echo "✓ 服务器程序已复制"
echo ""

# 4. 设置权限
echo "[4/5] 设置服务器程序权限..."
ssh ${BOARD_USER}@${BOARD_HOST} "chmod +x ${BOARD_DIR}/base_server.py"
echo "✓ 权限设置完成"
echo ""

# 5. 询问是否启动服务器
echo "[5/5] 部署完成！"
echo ""
echo "是否现在启动底盘服务器？"
echo "  输入 'yes' 启动服务器"
echo "  输入 'no' 稍后手动启动"
read -p "> " choice

if [ "$choice" = "yes" ] || [ "$choice" = "y" ]; then
    echo ""
    echo "正在连接到开发板并启动服务器..."
    echo "（按 Ctrl+C 停止服务器）"
    echo ""
    ssh ${BOARD_USER}@${BOARD_HOST} "cd ${BOARD_DIR} && python3 base_server.py"
else
    echo ""
    echo "稍后可以手动启动服务器："
    echo "  ssh ${BOARD_USER}@${BOARD_HOST}"
    echo "  cd ${BOARD_DIR}"
    echo "  python3 base_server.py"
    echo ""
    echo "或在后台运行："
    echo "  nohup python3 base_server.py > base_server.log 2>&1 &"
fi

echo ""
echo "=========================================="
echo "部署完成"
echo "=========================================="
