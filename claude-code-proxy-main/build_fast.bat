@echo off
echo === 开始构建 Claude Code Proxy Docker 镜像（快速版） ===

REM 使用快速构建的Dockerfile
docker compose --build-arg BUILDKIT_INLINE_CACHE=1 build

if %ERRORLEVEL% EQU 0 (
    echo ✅ 构建成功！
    echo === 启动服务 ===
    docker compose up -d
) else (
    echo ❌ 构建失败，请检查错误信息
    pause
)

pause