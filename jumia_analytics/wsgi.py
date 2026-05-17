"""
WSGI config for jumia_analytics project.
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jumia_analytics.settings')

application = get_wsgi_application()


def _ensure_admin():
    """Garantit que le compte admin existe et a le bon mot de passe au démarrage."""
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={'is_superuser': True, 'is_staff': True, 'is_active': True, 'email': ''}
        )
        # Toujours mettre à jour les droits et le mot de passe
        admin.set_password('admin123')
        admin.is_superuser = True
        admin.is_staff = True
        admin.is_active = True
        admin.save()
    except Exception:
        pass  # Ne jamais bloquer le démarrage du serveur


try:
    _ensure_admin()
except Exception:
    pass
