FROM python:3.12-slim

WORKDIR /app

# 只安装必要的运行时依赖，不需要编译！
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    fastapi \
    uvicorn[standard]==0.34.3 \
    pydantic \
    python-dotenv \
    openai \
    httpx

# 不复制源代码，使用volumes挂载支持热更新
# CMD ["python", "start_proxy.py"]

# 开发模式使用uvicorn的热重载
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8082", "--reload"]