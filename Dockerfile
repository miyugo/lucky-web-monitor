FROM python:3.9-slim
WORKDIR /app
RUN pip install fastapi uvicorn requests apscheduler -i https://pypi.tuna.tsinghua.edu.cn/simple
COPY main.py .
COPY index.html .
EXPOSE 8001
CMD ["python", "main.py"]
