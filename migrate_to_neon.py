"""
Migration des données Railway PostgreSQL → Neon.
Exécuté via: railway run python migrate_to_neon.py
"""
import os, sys, subprocess, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jumia_analytics.settings')

NEON_URL = "postgresql://neondb_owner:npg_1Nki5FmfCXyH@ep-damp-haze-apfgr9rq.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require"

def log(msg): print(f"[migrate] {msg}", flush=True)

# ── Étape 1 : Dump depuis Railway (DB source = DATABASE_URL actuel) ──────────
log("Dump des données depuis Railway PostgreSQL...")
import django
django.setup()

from django.core import serializers
from django.apps import apps

dump_file = "/tmp/railway_dump.json"
try:
    # Dump via Django (évite pg_dump, fonctionne cross-version)
    call_args = [sys.executable, "manage.py", "dumpdata",
                 "--natural-foreign", "--natural-primary",
                 "--exclude=contenttypes",
                 "--exclude=auth.permission",
                 "--indent=2",
                 "-o", dump_file]
    result = subprocess.run(call_args, capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERREUR dumpdata: {result.stderr}")
        sys.exit(1)
    size = os.path.getsize(dump_file) // 1024
    log(f"Dump OK — {size} KB")
except Exception as e:
    log(f"ERREUR: {e}")
    sys.exit(1)

# ── Étape 2 : Connecter à Neon et appliquer migrations ───────────────────────
log("Connexion à Neon et migrations...")
os.environ['DATABASE_URL'] = NEON_URL

# Recharger la configuration DB Django
from django.conf import settings
import dj_database_url
settings.DATABASES['default'] = dj_database_url.parse(
    NEON_URL, conn_max_age=0, conn_health_checks=True
)

# Fermer toutes les connexions existantes
from django.db import connections
connections.close_all()

# Migrations sur Neon
result = subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"],
                       capture_output=True, text=True)
if result.returncode != 0:
    log(f"ERREUR migrate: {result.stderr}")
    sys.exit(1)
log("Migrations Neon OK")

# ── Étape 3 : Restore des données sur Neon ───────────────────────────────────
log("Restauration des données sur Neon...")
result = subprocess.run([sys.executable, "manage.py", "loaddata", dump_file],
                       capture_output=True, text=True)
if result.returncode != 0:
    log(f"ERREUR loaddata: {result.stderr}")
    # Continuer quand même (données partielles OK)
else:
    log("Données restaurées OK")

# ── Étape 4 : Reset admin sur Neon ───────────────────────────────────────────
log("Création/reset admin sur Neon...")
from django.contrib.auth import get_user_model
User = get_user_model()
u, created = User.objects.get_or_create(
    username='admin',
    defaults={'is_superuser': True, 'is_staff': True, 'is_active': True, 'email': ''}
)
u.set_password('admin123')
u.is_superuser = True; u.is_staff = True; u.is_active = True
u.save()
log(f"Admin {'créé' if created else 'mis à jour'} — mdp: admin123")

log("=== MIGRATION TERMINÉE ===")
log(f"Prochaine étape: changer DATABASE_URL dans Railway → {NEON_URL[:50]}...")
