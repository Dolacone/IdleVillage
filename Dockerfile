FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY src/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY .env /app/.env
COPY .env.example /app/.env.example
COPY src/ .

RUN mkdir -p /app/data

CMD ["python", "main.py"]
