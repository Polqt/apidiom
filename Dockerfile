FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN python -m pip install --no-cache-dir -e .

ENV PORT=8000
CMD ["sh", "-c", "uvicorn apidiom.web.app:app --host 0.0.0.0 --port ${PORT}"]
