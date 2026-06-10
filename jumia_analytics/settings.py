import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Charger le fichier .env depuis la racine du projet
load_dotenv(BASE_DIR / '.env')

# Clé secrète (Railway utilisera une variable d'environnement)
SECRET_KEY = os.environ.get('SECRET_KEY', os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-pfe-jumia-2025-secret-key-123456789'))

# Debug : False en production
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

# Origines CSRF autorisées (Railway, Render, domaine custom)
_csrf = ['http://localhost:8000', 'http://127.0.0.1:8000']
if os.environ.get('RAILWAY_PUBLIC_DOMAIN'):
    _csrf.append(f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}")
if os.environ.get('RENDER_EXTERNAL_URL'):
    _csrf.append(os.environ['RENDER_EXTERNAL_URL'])
if os.environ.get('EXTRA_ALLOWED_HOSTS'):
    for h in os.environ['EXTRA_ALLOWED_HOSTS'].split(','):
        _csrf.append(f"https://{h.strip()}")
CSRF_TRUSTED_ORIGINS = _csrf

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'analytics',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # AJOUTER CETTE LIGNE
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'jumia_analytics.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'analytics' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'jumia_analytics.wsgi.application'

# Base de données
# Priorité : DATABASE_URL > NEON_DATABASE_URL > variables DB_* > SQLite
_db_url = os.environ.get('DATABASE_URL') or os.environ.get('NEON_DATABASE_URL')
if _db_url:
    import dj_database_url
    DATABASES = {'default': dj_database_url.parse(
        _db_url,
        conn_max_age=0,           # Ne pas réutiliser les connexions (évite SSL EOF)
        conn_health_checks=True,  # Vérifier la connexion avant chaque requête
    )}
elif os.environ.get('USE_SQLITE', 'True') != 'True':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'jumia_analytics'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/login/'

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Fichiers statiques (WhiteNoise)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'analytics' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}