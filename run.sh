#!/usr/bin/env bash
# ============================================================
# Agent Factory — 一键启动/管理脚本
# 初级开发者只需要记住这一个文件
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 彩色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

banner() {
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║      🏭  Agent Factory 控制台        ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════╝${NC}"
    echo ""
}

usage() {
    banner
    echo "使用方式:  ./run.sh [命令]"
    echo ""
    echo "命令:"
    echo "  start       一键启动（首次会自动构建）"
    echo "  stop        停止所有服务"
    echo "  restart     重启所有服务"
    echo "  logs        查看实时日志"
    echo "  status      查看服务状态"
    echo "  clean       完全清理（删除容器、镜像、构建缓存）"
    echo ""
    echo "启动后访问: ${GREEN}http://localhost:8080${NC}"
    echo ""
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ 未检测到 Docker，请先安装 Docker${NC}"
        echo "   安装指南: https://docs.docker.com/get-docker/"
        exit 1
    fi
    if ! docker compose version &> /dev/null; then
        echo -e "${RED}❌ 未检测到 Docker Compose，请升级 Docker${NC}"
        exit 1
    fi
}

check_env() {
    if [ ! -f "${ROOT_DIR}/.env" ]; then
        echo -e "${YELLOW}⚠️  未检测到 .env 文件，正在从模板创建...${NC}"
        if [ -f "${ROOT_DIR}/.env.example" ]; then
            cp "${ROOT_DIR}/.env.example" "${ROOT_DIR}/.env"
            echo -e "${YELLOW}📝 已创建 .env 文件，请编辑填入你的 API Key 后重新启动${NC}"
            echo -e "   ${GREEN}vim ${ROOT_DIR}/.env${NC}"
            echo ""
            echo -e "${RED}⏸️  请先配置 API Key 再启动${NC}"
            exit 0
        else
            echo -e "${RED}❌ 缺少 .env.example 模板文件${NC}"
            exit 1
        fi
    fi
}

cmd_start() {
    check_docker
    check_env

    # 检查是否已在运行
    if docker compose ps --services --filter "status=running" 2>/dev/null | grep -q .; then
        echo -e "${GREEN}✅ 服务已在运行中${NC}"
        echo -e "   访问: ${GREEN}http://localhost:8080${NC}"
        return
    fi

    echo -e "${BLUE}🚀 正在启动 Agent Factory ...${NC}"
    docker compose up -d --build

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  ✅ Agent Factory 启动成功！         ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║  访问地址: http://localhost:8080     ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════╝${NC}"
    echo ""
}

cmd_stop() {
    check_docker
    echo -e "${BLUE}🛑 正在停止 Agent Factory ...${NC}"
    docker compose down
    echo -e "${GREEN}✅ 已停止${NC}"
}

cmd_restart() {
    check_docker
    echo -e "${BLUE}🔄 正在重启 Agent Factory ...${NC}"
    docker compose down
    docker compose up -d --build
    echo -e "${GREEN}✅ 重启完成${NC}"
    echo -e "   访问: ${GREEN}http://localhost:8080${NC}"
}

cmd_logs() {
    check_docker
    docker compose logs -f --tail=50
}

cmd_status() {
    check_docker
    echo ""
    echo -e "${BLUE}=== Agent Factory 服务状态 ===${NC}"
    echo ""
    docker compose ps
    echo ""
    echo -e "访问地址: ${GREEN}http://localhost:8080${NC}"
    echo ""
}

cmd_clean() {
    check_docker
    echo -e "${RED}⚠️  这将删除所有容器、镜像和构建缓存${NC}"
    read -p "确认继续？[y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker compose down -v --rmi all --remove-orphans
        echo -e "${GREEN}✅ 清理完成${NC}"
    else
        echo "已取消"
    fi
}

# === 主入口 ===
cd "${ROOT_DIR}"

case "${1:-}" in
    start)
        cmd_start
        ;;
    stop)
        cmd_stop
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        cmd_logs
        ;;
    status)
        cmd_status
        ;;
    clean)
        cmd_clean
        ;;
    *)
        usage
        ;;
esac
