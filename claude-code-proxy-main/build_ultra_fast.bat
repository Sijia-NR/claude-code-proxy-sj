@echo off
echo === 超速构建 Claude Code Proxy ===

REM 强制使用不编译的Dockerfile
if exist Dockerfile del Dockerfile
copy Dockerfile.no-compile Dockerfile

REM 使用--no-cache加速构建
echo 正在构建（可能需要1-2分钟）...
docker compose build --no-cache --progress=plain

if %ERRORLEVEL% EQU 0 (
    echo ✅ 构建成功！
    echo === 启动服务 ===
    docker compose up -d

    echo === 等待服务启动... ===
    timeout /t 5 /nobreak > nul

    echo === 测试服务 ===
    curl http://localhost:8082/health
) else (
    echo ❌ 构建失败
)

pause