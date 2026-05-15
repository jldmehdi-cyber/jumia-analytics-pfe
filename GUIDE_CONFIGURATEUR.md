# Guide du Configurateur de KPIs

## Vue d'ensemble

Le **configurateur de KPIs** permet à chaque utilisateur de personnaliser entièrement son expérience analytique :

1. **Créer ses propres indicateurs** (KPIs)
2. **Générer un canevas Excel** adapté à sa structure de données
3. **Importer ses données** via le canevas rempli
4. **Visualiser un dashboard** généré dynamiquement selon ses KPIs

---

## Étape 1 : Créer vos Indicateurs

### Accéder au configurateur
```
Dashboard → Bouton "Configurer mes KPIs" → Onglet "Mes Indicateurs"
```

### Types de calcul disponibles

| Type | Description | Exemple |
|------|-------------|---------|
| **Somme** | Additionne les valeurs | CA total, Marge totale |
| **Moyenne** | Valeur moyenne | Panier moyen, Prix moyen |
| **Compte** | Nombre d'éléments distincts | Nb clients, Nb produits |
| **Minimum** | Valeur la plus basse | Prix minimum |
| **Maximum** | Valeur la plus haute | Prix maximum |
| **Ratio** | Division de deux champs | Taux de conversion |
| **Pourcentage** | Variation période précédente | Croissance |
| **Formule** | Expression personnalisée | CAC, LTV, Rentabilité |

### Exemples d'indicateurs personnalisés

```
Code: ca_total
Nom: Chiffre d'Affaires Total
Type calcul: Somme
Champ source: ca_ligne
Type affichage: Montant (DZD)
Icône: fa-coins

Code: panier_moyen
Nom: Panier Moyen
Type calcul: Formule
Formule: ca / nb_commandes
Type affichage: Montant (DZD)

Code: taux_conversion
Nom: Taux de Conversion
Type calcul: Ratio
Numérateur: nb_achats
Dénominateur: nb_vues
Type affichage: Pourcentage
Seuil alerte min: 2.0
```

---

## Étape 2 : Générer le Canevas Excel

### Onglet "Canevas de Saisie"

1. Sélectionnez votre **configuration projet**
2. Ajoutez des **colonnes personnalisées** si besoin :
   - Canal d'acquisition
   - Coût marketing
   - Satisfaction client (NPS)
   - etc.
3. Cliquez sur **"Télécharger le Canevas Excel"**

### Structure du canevas généré

Le fichier Excel contient :
- **Feuille "Données à saisir"** : Colonnes préformatées avec exemples
- **Feuille "Instructions"** : Documentation de chaque colonne

### Colonnes de base (toujours présentes)

| Colonne | Type | Obligatoire |
|---------|------|-------------|
| Date | Date | Oui |
| Code Client | Texte | Oui |
| Nom Client | Texte | Non |
| Région | Texte | Non |
| Code Article | Texte | Oui |
| Nom Article | Texte | Non |
| Catégorie | Texte | Non |
| Code Commercial | Texte | Non |
| Nom Commercial | Texte | Non |
| Quantité | Nombre | Oui |
| Prix Unitaire | Montant | Oui |
| Remise (%) | Pourcentage | Non |

### Colonnes personnalisées (exemples)

```json
[
  {"nom": "Canal", "type": "texte", "obligatoire": false},
  {"nom": "CoutMarketing", "type": "montant", "obligatoire": false},
  {"nom": "NPS", "type": "nombre", "obligatoire": false}
]
```

---

## Étape 3 : Remplir et Importer

### Remplissage du canevas

1. Ouvrez le fichier Excel téléchargé
2. Remplissez les lignes avec vos données
3. Respectez les formats (dates en YYYY-MM-DD, montants sans devise)
4. **Ne modifiez pas les noms des colonnes**

### Import

1. Retournez sur le configurateur → Onglet "Canevas"
2. Sélectionnez votre configuration
3. **Glissez-déposez** votre fichier Excel ou cliquez pour parcourir
4. Le système valide et importe automatiquement

### Résultat de l'import

```json
{
  "imported": 1523,
  "errors": ["Ligne 45: Quantité négative"],
  "total_rows": 1524
}
```

---

## Étape 4 : Configurer les Widgets

### Onglet "Widgets"

Associez chaque indicateur à un type de visualisation :

| Type de Widget | Usage | Indicateur adapté |
|----------------|-------|-------------------|
| **Carte KPI** | Valeur simple avec tendance | CA, Marge, Nb clients |
| **Graphique ligne** | Évolution temporelle | CA mensuel, Tendance |
| **Graphique barres** | Comparaison | CA par région, Par commercial |
| **Graphique circulaire** | Répartition | Mix produit, Segments |
| **Tableau** | Données détaillées | Top articles, Top clients |
| **Jauge** | Performance vs objectif | Taux de conversion |

### Positionnement

- **Largeur** : 1 à 12 (sur une grille de 12 colonnes)
- **Hauteur** : 1 à 12
- **Position X/Y** : Coordonnées sur la grille

---

## Étape 5 : Visualiser le Dashboard

Retournez au **Dashboard principal**. Les widgets configurés apparaissent automatiquement avec vos données importées.

---

## Formules personnalisées avancées

### Variables disponibles

| Variable | Description |
|----------|-------------|
| `ca` | Chiffre d'affaires total |
| `marge` | Marge totale |
| `nb_commandes` | Nombre de commandes |
| `quantite` | Quantité totale vendue |
| `panier_moyen` | Panier moyen (ca / nb_commandes) |

### Exemples de formules

```python
# Coût d'Acquisition Client (CAC)
formule = "50000 / nb_commandes"

# Rentabilité par commande
formule = "marge / nb_commandes"

# Taux de marge
formule = "(marge / ca) * 100"

# Valeur Vie Client (LTV) estimée
formule = "panier_moyen * 12"  # 12 achats par an estimés
```

---

## Dimensions d'analyse (Drill-down)

Configurez les dimensions pour découper vos analyses :

| Dimension | Champ SQL | Usage |
|-----------|-----------|-------|
| Région | `region` | CA par région géographique |
| Catégorie | `categorie` | Performance par famille produit |
| Commercial | `code_commercial` | Classement des vendeurs |
| Client | `code_client` | Analyse par client |
| Mois | `date_transaction__month` | Saisonnalité |
| Année | `date_transaction__year` | Évolution annuelle |

---

## Cas d'usage

### Cas 1 : Retail classique
```
Indicateurs: CA, Marge, Panier moyen, Nb clients
Dimensions: Région, Catégorie, Commercial
```

### Cas 2 : E-commerce avec comportement
```
Indicateurs: CA, Taux conversion, Panier abandonné, NPS
Dimensions: Canal, Catégorie, Source trafic
Colonnes perso: Canal, CoutMarketing, NPS
```

### Cas 3 : B2B avec rentabilité
```
Indicateurs: CA, Marge, CAC, LTV, Délai paiement
Dimensions: Commercial, Secteur client, Taille client
Colonnes perso: Secteur, TailleClient, DelaiPaiement
```

---

## API Endpoints du Configurateur

| Endpoint | Méthode | Description |
|----------|---------|-------------|
| `/api/indicateurs/` | GET/POST | Liste / Créer |
| `/api/indicateurs/<id>/` | GET/PUT/DELETE | Détail / Modifier / Supprimer |
| `/api/indicateurs/<id>/calculer/` | POST | Calculer la valeur |
| `/api/configurations/` | GET/POST | Configurations projet |
| `/api/configurations/<id>/canevas/` | GET | Générer Excel |
| `/api/configurations/<id>/importer/` | POST | Importer données |
| `/api/widgets/` | GET/POST | Widgets dashboard |
| `/api/dashboard-dynamique/` | GET | Dashboard complet |
