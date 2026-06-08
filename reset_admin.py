"""Script de reset admin — appelé au démarrage Railway."""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jumia_analytics.settings')
django.setup()

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
print(f"[reset_admin] admin {'cree' if created else 'mis a jour'} — mdp: admin123")
