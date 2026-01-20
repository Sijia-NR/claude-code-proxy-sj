@echo off
echo === 开发模式启动（支持热更新） ===

REM 停止现有服务
docker compose down

REM 构建镜像（只第一次需要）
echo 首次构建镜像...
docker compose -f docker-compose.dev.yml build --no-cache

if %ERRORLEVEL% NEQ 0 (
    echo ❌ 构建失败
    pause
    exit /b 1
)

REM 启动开发服务
echo 启动开发服务（支持代码热更新）...
docker compose -f docker-compose.dev.yml up -d

REM 等待服务启动
echo 等待服务启动...
timeout /t 5 /nobreak > nul

REM 检查服务状态
echo === 服务状态 ===
docker compose -f docker-compose.dev.yml ps

REM 测试服务
echo === 测试连接 ===
curl -s http://localhost:8082/health

echo.
echo ✅ 开发环境已启动！
echo 💡 修改代码后服务会自动重启
echo 📝 查看日志: docker compose -f docker-compose.dev.yml logs -f
echo 🛑 停止服务: docker compose -f docker-compose.dev.yml down

pause