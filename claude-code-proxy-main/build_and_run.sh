#!/bin/bash
echo "=== 开始构建 Claude Code Proxy Docker 镜像 ==="

# 设置加速构建的参数
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

# 使用国内镜像源加速（如果可用）
if command -v docker &> /dev/null; then
    echo "使用 Docker BuildKit 加速构建..."

    # 构建镜像
    docker compose --build-arg BUILDKIT_INLINE_CACHE=1 build

    if [ $? -eq 0 ]; then
        echo "✅ 构建成功！"
        echo "=== 启动服务 ==="
        docker compose up -d
    else
        echo "❌ 构建失败，请检查错误信息"
    fi
else
    echo "Docker 未找到，请确保 Docker 已安装并运行"
fi