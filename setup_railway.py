import os
import sys

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jumia_analytics.settings')

import django
django.setup()

from django.core.management import call_command
from django.contrib.auth import get_user_model

def setup_railway():
    print("=" * 60)
    print("🔧 SETUP AUTOMATIQUE RAILWAY")
    print("=" * 60)
    print()

    # 1. Vérifier la connexion base de données
    print("📊 Étape 1 : Vérification de la base de données...")
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            print("   ✅ Connexion base de données OK")
    except Exception as e:
        print(f"   ❌ Erreur base de données : {e}")
        return False

    # 2. Appliquer les migrations
    print()
    print("📊 Étape 2 : Application des migrations...")
    try:
        call_command('migrate', '--noinput')
        print("   ✅ Migrations appliquées")
    except Exception as e:
        print(f"   ❌ Erreur migrations : {e}")
        return False

    # 3. Créer le superutilisateur
    print()
    print("📊 Étape 3 : Création du superutilisateur...")
    try:
        User = get_user_model()
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', '', 'admin123')
            print("   ✅ Superutilisateur 'admin' créé")
            print("   🔑 Password : admin123")
        else:
            print("   ℹ️ Superutilisateur 'admin' existe déjà")
            # Réinitialiser le mot de passe
            user = User.objects.get(username='admin')
            user.set_password('admin123')
            user.save()
            print("   🔄 Mot de passe réinitialisé à 'admin123'")
    except Exception as e:
        print(f"   ❌ Erreur création superutilisateur : {e}")
        return False

    # 4. Collecter les fichiers statiques
    print()
    print("📊 Étape 4 : Collecte des fichiers statiques...")
    try:
        call_command('collectstatic', '--noinput', '--clear')
        print("   ✅ Fichiers statiques collectés")
    except Exception as e:
        print(f"   ⚠️ Avertissement fichiers statiques : {e}")

    # 5. Vérification finale
    print()
    print("=" * 60)
    print("✅ SETUP TERMINÉ AVEC SUCCÈS")
    print("=" * 60)
    print()
    print("📍 URLs disponibles :")
    print("   🏠 Dashboard    : /")
    print("   ⚙️ Admin Django : /admin/")
    print("   📊 Configurator : /configurator/")
    print()
    print("🔑 Identifiants :")
    print("   Username : admin")
    print("   Password : admin123")
    print()

    return True

if __name__ == "__main__":
    success = setup_railway()
    sys.exit(0 if success else 1)
