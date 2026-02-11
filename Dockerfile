FROM python:3.9-slim
WORKDIR /app
RUN pip install fastapi uvicorn requests apscheduler -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY main.py .
COPY index.html .
# 暴露 8001 端口
EXPOSE 8001
# 启动模块 main:app，端口 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
