#!/bin/bash
set -e

echo "==> Migrations..."
python manage.py migrate --no-input

echo "==> Reset admin password..."
python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
u, created = User.objects.get_or_create(
    username='admin',
    defaults={'is_superuser': True, 'is_staff': True, 'is_active': True, 'email': ''}
)
u.set_password('admin123')
u.is_superuser = True
u.is_staff = True
u.is_active = True
u.save()
print('Admin OK — mot de passe : admin123')
"

echo "==> Collectstatic..."
python manage.py collectstatic --noinput --clear

echo "==> Starting Gunicorn..."
exec gunicorn jumia_analytics.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120 --preload
