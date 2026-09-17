FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml .

RUN pip install fastapi uvicorn requests

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]