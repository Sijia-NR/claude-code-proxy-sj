#!/bin/bash
echo "=== 开发模式启动（支持热更新） ==="

# 停止现有服务
docker compose down

# 构建镜像（只第一次需要）
echo "首次构建镜像..."
docker compose -f docker-compose.dev.yml build --no-cache

# 启动开发服务
echo "启动开发服务（支持代码热更新）..."
docker compose -f docker-compose.dev.yml up -d

# 等待服务启动
echo "等待服务启动..."
sleep 5

# 检查服务状态
docker compose -f docker-compose.dev.yml ps

# 测试服务
echo "测试服务连接..."
curl -s http://localhost:8082/health && echo ""

echo "✅ 开发环境已启动！"
echo "💡 修改代码后服务会自动重启"
echo "📝 查看日志: docker compose -f docker-compose.dev.yml logs -f"
echo "🛑 停止服务: docker compose -f docker-compose.dev.yml down"