import os
import sys

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jumia_analytics.settings')

# Forcer SQLite locale (pas besoin de PostgreSQL pour cette étape)
os.environ['USE_SQLITE'] = 'True'

import django
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

# Créer le superutilisateur
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', '', 'admin123')
    print('✅ Superutilisateur "admin" créé avec succès !')
    print('   Username: admin')
    print('   Password: admin123')
else:
    print('ℹ️ Le superutilisateur "admin" existe déjà.')
    print('   Username: admin')
    print('   Password: admin123')
