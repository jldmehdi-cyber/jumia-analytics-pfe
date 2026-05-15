# Jumia Analytics - Django 5.2 LTS
FROM python:3.11-slim

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code
COPY . .

# Collect static
RUN python manage.py collectstatic --noinput

# Expose
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/ || exit 1

# Démarrage
CMD ["gunicorn", "jumia_analytics.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4"]
