import subprocess
import sys
import json

def get_railway_url():
    """Récupère l'URL publique de l'application Railway"""
    try:
        # Vérifier si Railway CLI est installé
        result = subprocess.run(['railway', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            print("❌ Railway CLI n'est pas installé.")
            print("   Installe-le avec : npm install -g @railway/cli")
            return None

        # Récupérer l'URL du service
        result = subprocess.run(['railway', 'domain'], 
                              capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            url = result.stdout.strip()
            if url:
                return url

        # Alternative : utiliser railway status
        result = subprocess.run(['railway', 'status', '--json'], 
                              capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            data = json.loads(result.stdout)
            # Extraire l'URL des données
            services = data.get('services', [])
            for service in services:
                domain = service.get('domain')
                if domain:
                    return domain

        return None

    except FileNotFoundError:
        print("❌ Railway CLI n'est pas trouvé.")
        print("   Installe-le avec : npm install -g @railway/cli")
        return None
    except Exception as e:
        print(f"❌ Erreur : {e}")
        return None

def main():
    print("=" * 50)
    print("🔍 RÉCUPÉRATION DE L'URL RAILWAY")
    print("=" * 50)
    print()

    url = get_railway_url()

    if url:
        print(f"✅ URL de ton application :")
        print(f"   {url}")
        print()
        print("📍 URLs disponibles :")
        print(f"   🏠 Dashboard    : {url}/")
        print(f"   ⚙️ Admin Django : {url}/admin/")
        print(f"   📊 Configurator : {url}/configurator/")
        print()
        print("🔑 Identifiants Admin :")
        print("   Username : admin")
        print("   Password : admin123")
        print()
        print("=" * 50)

        # Sauvegarder dans un fichier
        with open('railway_url.txt', 'w') as f:
            f.write(f"URL: {url}\n")
            f.write(f"Admin: {url}/admin/\n")
            f.write("Username: admin\n")
            f.write("Password: admin123\n")
        print("💾 URL sauvegardée dans 'railway_url.txt'")

    else:
        print("❌ Impossible de récupérer l'URL automatiquement.")
        print()
        print("📝 Méthode manuelle :")
        print("   1. Va sur https://railway.app")
        print("   2. Clique sur ton projet")
        print("   3. Clique sur ton service (jumia-analytics-pfe)")
        print("   4. L'URL est affichée en haut de la page")
        print()
        print("🌐 L'URL suit ce format :")
        print("   https://[nom-service]-[nom-projet].up.railway.app")

if __name__ == "__main__":
    main()
