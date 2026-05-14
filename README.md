# Jumia Analytics — PFE Big Data

**Dashboard analytique intelligent** aligné avec le mémoire PFE : Django 5.2 LTS (Avril 2025 - Avril 2028) + PostgreSQL + Chatbot NLP + Données comportementales.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Couche Présentation : Django Templates + Chart.js      │
│  Couche API          : Django REST Framework + JWT      │
│  Couche Données      : PostgreSQL (modèle en étoile)     │
│  Couche IA           : NLTK + Scikit-learn (chatbot)    │
│  Couche Collecte     : Logs web + Transactions           │
└─────────────────────────────────────────────────────────┘
```

## Fonctionnalités

### 🎛️ Configuration des KPIs (Nouveau)
- **Création d'indicateurs personnalisés** : Somme, Moyenne, Compte, Ratio, Formule
- **Générateur de canevas Excel** : Template préformaté pour la saisie des données
- **Import flexible** : Adapte la structure selon les colonnes configurées
- **Dashboard adaptatif** : Widgets générés dynamiquement selon les KPIs choisis
- **Seuils d'alerte configurables** : Par indicateur, avec couleurs personnalisables

### KPIs (§4.1.1)
- Chiffre d'affaires, marge, panier moyen, nombre de clients
- Filtrage par région et période
- Comparaison période précédente (croissance)

### Analyse Temporelle (§4.1.2)
- Évolution mensuelle du CA et de la marge
- Graphiques interactifs avec Chart.js

### Segmentation RFM (§4.1.3)
- 6 segments : Champions, Fidèles, Potentiels, Nouveaux, Perdus, Hibernation
- Scores R, F, M calculés automatiquement

### Données Comportementales (§4.2)
- **Funnel de conversion** : Vues → Ajouts panier → Achats
- **Produits fantômes** : Ratio vues/achats > 50:1
- **Produits cachés** : Faibles vues, haute conversion
- **Points de friction** : Pages avec abandons élevés
- **Segmentation comportementale** : 5 segments de navigation

### Chatbot Analytique (§4.3)
- Pipeline NLP : Tokenisation → Lemmatisation → Stop words → TF-IDF
- **VotingClassifier** : SVM + Random Forest + Régression Logistique
- 6 intentions : KPI, Comparaison, Tendance, Anomalie, Produit, Catégorie
- Fallback intelligent (seuil de confiance 40%)
- Génération de requêtes SQL paramétrées

### Prédictions ML
- Régression polynomiale pour prévisions de ventes
- Isolation Forest pour détection d'anomalies

### Exports
- Excel (.xlsx) avec résumé
- CSV

## Installation

### 1. Cloner et installer
```bash
git clone <repo>
cd jumia_analytics
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Base de données
```bash
# Option A: PostgreSQL (recommandé)
createdb jumia_analytics
# Modifier jumia_analytics/settings.py avec vos credentials

# Option B: SQLite (développement rapide)
export USE_SQLITE=True
```

### 3. Migrations et superuser
```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. Importer les données
```bash
# Placer ETAT.xlsx dans data/
python manage.py import_data --file data/ETAT.xlsx --n-sessions 5000
```

### 5. Lancer
```bash
python manage.py runserver
# → http://localhost:8000
```

## Déploiement

### Railway (Recommandé)
```bash
# 1. Créer un projet sur railway.app
# 2. Ajouter PostgreSQL
# 3. Connecter le repo Git
# 4. Variables d'environnement :
#    - DJANGO_SECRET_KEY=<clé secrète>
#    - DB_NAME=jumia_analytics
#    - DB_USER=postgres
#    - DB_PASSWORD=<mot de passe>
#    - DB_HOST=<host railway>
#    - JWT_SECRET=<clé jwt>
# 5. Deploy
```

### Docker
```bash
docker build -t jumia-analytics .
docker run -p 8000:8000 -e DJANGO_SECRET_KEY=xxx -e DB_HOST=xxx jumia-analytics
```

## API Endpoints

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/auth/login/` | POST | Authentification JWT |
| `/api/health/` | GET | Health check |
| `/api/kpis/` | GET | KPIs globaux |
| `/api/tendances/` | GET | Évolution temporelle |
| `/api/rfm/` | GET | Segmentation RFM |
| `/api/par-region/` | GET | CA par région |
| `/api/par-article/` | GET | Top articles |
| `/api/funnel/` | GET | Funnel conversion |
| `/api/produits-fantomes/` | GET | Produits fantômes |
| `/api/produits-caches/` | GET | Produits cachés |
| `/api/points-friction/` | GET | Points de friction |
| `/api/segmentation-comportementale/` | GET | Segments comportementaux |
| `/api/chatbot/` | POST | Chatbot NLP |
| `/api/previsions/` | GET | Prévisions ML |
| `/api/alertes/` | GET | Alertes anomalies |
| `/api/export/excel/` | GET | Export Excel |
| `/api/export/csv/` | GET | Export CSV |

## Structure du Projet

```
jumia_analytics/
├── jumia_analytics/      # Config Django
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── analytics/            # App principale
│   ├── models.py         # 8 entités relationnelles
│   ├── views.py          # 20+ endpoints API
│   ├── chatbot_engine.py # Pipeline NLP + VotingClassifier
│   ├── middleware.py     # Logging requêtes
│   ├── admin.py          # Django Admin
│   ├── management/
│   │   └── commands/
│   │       └── import_data.py  # Migration Excel→PG
│   ├── templates/
│   │   └── analytics/
│   │       ├── dashboard.html  # SPA complète
│   │       └── login.html
│   └── static/
│       ├── css/
│       └── js/
├── data/
│   └── ETAT.xlsx
├── requirements.txt
├── Procfile
├── Dockerfile
└── README.md
```

## Technologies

- **Backend** : Django 5.2 LTS (Avril 2025 - Avril 2028), Django REST Framework, JWT Auth
- **Base de données** : PostgreSQL (modèle en étoile)
- **Frontend** : Chart.js, Vanilla JS, Dark Theme
- **ML/NLP** : Scikit-learn (VotingClassifier), NLTK
- **Déploiement** : Docker, Gunicorn, Railway/Render

## Licence

Projet académique — PFE Big Data Analytics 2025
