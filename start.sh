#!/bin/bash
# Pas de set -e : on continue même si une étape non-critique échoue

echo "===== DEMARRAGE JUMIA ANALYTICS ====="
echo "Python: $(python --version)"
echo "Workdir: $(pwd)"

echo ""
echo "==> [1/4] Migrations..."
python manage.py migrate --no-input
if [ $? -ne 0 ]; then
    echo "AVERTISSEMENT: migrations echouees (peut-etre deja a jour)"
fi

echo ""
echo "==> [2/4] Reset mot de passe admin..."
python manage.py shell << 'PYEOF'
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
print(f"Admin {'cree' if created else 'mis a jour'} — mot de passe: admin123")
PYEOF

echo ""
echo "==> [3/4] Collectstatic..."
python manage.py collectstatic --noinput 2>&1 || echo "AVERTISSEMENT: collectstatic a echoue (non-bloquant)"

echo ""
echo "==> [4/4] Demarrage Gunicorn sur port ${PORT:-8000}..."
exec gunicorn jumia_analytics.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --preload \
    --log-level info
