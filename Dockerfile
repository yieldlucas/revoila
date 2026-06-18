FROM python:3.11-slim

WORKDIR /app

# Dépendances d'abord (cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code
COPY . .

ENV PORT=8000
EXPOSE 8000

# En prod, définir DRY_RUN=false et les clés via variables d'environnement.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
