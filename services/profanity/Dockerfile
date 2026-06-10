FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY profanity ./profanity

EXPOSE 50052
CMD ["python", "-m", "app.server"]
