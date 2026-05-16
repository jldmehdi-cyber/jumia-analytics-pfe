# Jumia Analytics - Django 5.2 LTS
FROM python:3.11-slim

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Code
COPY . .

# Variables pour le build (pas de DB disponible pendant le build)
ENV DJANGO_SETTINGS_MODULE=jumia_analytics.settings \
    SECRET_KEY=build-secret-key-placeholder \
    DEBUG=False \
    USE_SQLITE=True

# Collect static (utilise SQLite temporairement pendant le build)
RUN python manage.py collectstatic --noinput

# Expose
EXPOSE 8000

# Démarrage : migrate puis gunicorn sur $PORT
CMD sh -c "python manage.py migrate --noinput && gunicorn jumia_analytics.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 120"
