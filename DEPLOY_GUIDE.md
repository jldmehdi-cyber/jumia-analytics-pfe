# Guide de Déploiement — Jumia Analytics

## Option 1 : Railway (Recommandé pour PFE)

### Étape 1 : Préparer le projet
```bash
cd jumia_analytics
git init
git add .
git commit -m "Initial commit"
```

### Étape 2 : Créer un projet Railway
1. Aller sur [railway.app](https://railway.app)
2. Créer un compte (GitHub login)
3. **New Project** → **Deploy from GitHub repo**
4. Sélectionner votre repo

### Étape 3 : Ajouter PostgreSQL
1. Dans le projet Railway, cliquer **New** → **Database** → **Add PostgreSQL**
2. Railway crée automatiquement les variables d'environnement

### Étape 4 : Variables d'environnement
Dans **Variables** → **New Variable** :

```
DJANGO_SECRET_KEY=votre-cle-super-secrete-123456789
JWT_SECRET=votre-jwt-secret-987654321
DEBUG=False
ALLOWED_HOSTS=votre-app.up.railway.app,localhost
```

### Étape 5 : Deploy
Railway déploie automatiquement à chaque `git push`.

### Étape 6 : Migrations initiales
```bash
# Dans l'interface Railway → votre service → Shell
python manage.py migrate
python manage.py createsuperuser
python manage.py import_data --file data/ETAT.xlsx
```

---

## Option 2 : Render

### Étape 1 : Créer un compte Render
[render.com](https://render.com) → Sign up with GitHub

### Étape 2 : New Web Service
- **Build Command** : `pip install -r requirements.txt && python manage.py collectstatic --noinput`
- **Start Command** : `gunicorn jumia_analytics.wsgi:application`

### Étape 3 : PostgreSQL
- **New** → **PostgreSQL**
- Copier l'Internal Connection String dans les variables d'env

### Étape 4 : Variables
```
PYTHON_VERSION=3.11.0
DJANGO_SECRET_KEY=xxx
JWT_SECRET=xxx
DATABASE_URL=postgresql://...  # Fourni par Render
```

---

## Option 3 : Ngrok (Démo rapide)

```bash
# 1. Installer ngrok
# https://ngrok.com/download

# 2. Lancer l'app localement
python manage.py runserver 0.0.0.0:8000

# 3. Exposer
ngrok http 8000

# 4. URL temporaire affichée (ex: https://abc123.ngrok-free.app)
# Partager cette URL au jury !
```

**⚠️ Limitation** : L'URL change à chaque redémarrage. PC doit rester allumé.

---

## Vérification post-déploiement

```bash
# Health check
curl https://votre-app.up.railway.app/api/health/

# Login
curl -X POST https://votre-app.up.railway.app/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"votre_mdp"}'
```

## Dépannage

| Problème | Solution |
|----------|----------|
| `ModuleNotFoundError` | Vérifier requirements.txt |
| `Static files 404` | `python manage.py collectstatic` |
| `Database error` | Vérifier DATABASE_URL / credentials |
| `CORS blocked` | Ajouter le domaine dans CORS_ALLOWED_ORIGINS |
| `Chatbot lent` | Première requête entraîne le modèle (normal) |
