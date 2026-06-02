FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY metapod ./metapod

EXPOSE 50051
CMD ["python", "-m", "app.server"]
