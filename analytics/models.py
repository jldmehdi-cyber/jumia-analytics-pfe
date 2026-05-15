"""
Modèles de données alignés avec le mémoire PFE §2.2.2
Architecture en étoile + données comportementales + chatbot + KPIs configurables
"""
from django.db import models
from django.contrib.auth.models import User
import uuid


# ═════════════════════════════════════════════
# MODÈLES DE BASE (Mémoire §2.2.2)
# ═════════════════════════════════════════════

class Categorie(models.Model):
    """Dimension catégorie de produit"""
    id_categorie = models.AutoField(primary_key=True)
    nom_categorie = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dim_categorie'
        verbose_name = 'Catégorie'
        verbose_name_plural = 'Catégories'

    def __str__(self):
        return self.nom_categorie


class Produit(models.Model):
    """Dimension produit"""
    id_produit = models.AutoField(primary_key=True)
    code_article = models.CharField(max_length=50, unique=True)
    nom_article = models.CharField(max_length=200)
    categorie = models.ForeignKey(Categorie, on_delete=models.CASCADE, related_name='produits')
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    cout_unitaire = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    marge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_disponible = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dim_produit'
        verbose_name = 'Produit'
        verbose_name_plural = 'Produits'

    def __str__(self):
        return f"{self.code_article} - {self.nom_article}"

    def save(self, *args, **kwargs):
        self.marge = self.prix_unitaire - self.cout_unitaire
        super().save(*args, **kwargs)


class Client(models.Model):
    """Dimension client avec segmentation RFM"""
    SEGMENTS = [
        ('champions', 'Champions'),
        ('clients_fideles', 'Clients Fidèles'),
        ('clients_potentiels', 'Clients Potentiels'),
        ('nouveaux', 'Nouveaux Clients'),
        ('clients_perdus', 'Clients Perdus'),
        ('hibernation', 'En Hibernation'),
    ]

    id_client = models.AutoField(primary_key=True)
    code_client = models.CharField(max_length=50, unique=True)
    nom_client = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)
    telephone = models.CharField(max_length=20, blank=True, null=True)
    ville = models.CharField(max_length=100, blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)

    # Segmentation RFM
    recence = models.IntegerField(default=0)
    frequence = models.IntegerField(default=0)
    montant = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    segment_rfm = models.CharField(max_length=20, choices=SEGMENTS, default='nouveaux')
    score_rfm = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'dim_client'
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'

    def __str__(self):
        return f"{self.code_client} - {self.nom_client}"


class Commercial(models.Model):
    """Dimension commercial"""
    id_commercial = models.AutoField(primary_key=True)
    code_commercial = models.CharField(max_length=50, unique=True)
    nom_commercial = models.CharField(max_length=200)
    email = models.EmailField(blank=True, null=True)
    zone = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dim_commercial'
        verbose_name = 'Commercial'
        verbose_name_plural = 'Commerciaux'

    def __str__(self):
        return f"{self.code_commercial} - {self.nom_commercial}"


class Commande(models.Model):
    """Table de faits : Commandes"""
    id_commande = models.AutoField(primary_key=True)
    numero_commande = models.CharField(max_length=50, unique=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='commandes')
    commercial = models.ForeignKey(Commercial, on_delete=models.SET_NULL, null=True, related_name='commandes')
    date_commande = models.DateField()
    mois = models.IntegerField()
    annee = models.IntegerField()
    trimestre = models.IntegerField()

    total_ht = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_ttc = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remise = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fait_commande'
        verbose_name = 'Commande'
        verbose_name_plural = 'Commandes'
        indexes = [
            models.Index(fields=['date_commande']),
            models.Index(fields=['client', 'date_commande']),
            models.Index(fields=['commercial', 'annee', 'mois']),
        ]

    def __str__(self):
        return f"CMD-{self.numero_commande}"


class LigneCommande(models.Model):
    """Table de faits : Lignes de commande"""
    id_ligne = models.AutoField(primary_key=True)
    commande = models.ForeignKey(Commande, on_delete=models.CASCADE, related_name='lignes')
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='lignes_commande')
    quantite = models.IntegerField(default=1)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2)
    remise_ligne = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    ca_ligne = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    marge_ligne = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fait_ligne_commande'
        verbose_name = 'Ligne de commande'
        verbose_name_plural = 'Lignes de commande'

    def save(self, *args, **kwargs):
        self.ca_ligne = self.quantite * self.prix_unitaire * (1 - self.remise_ligne / 100)
        if self.produit:
            self.marge_ligne = self.quantite * (self.prix_unitaire - self.produit.cout_unitaire)
        super().save(*args, **kwargs)


# ═════════════════════════════════════════════
# DONNÉES COMPORTEMENTALES (§4.2)
# ═════════════════════════════════════════════

class SessionNavigation(models.Model):
    """Session de navigation utilisateur"""
    id_session = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True, related_name='sessions')
    ip_adresse = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    date_debut = models.DateTimeField(auto_now_add=True)
    date_fin = models.DateTimeField(blank=True, null=True)
    duree_secondes = models.IntegerField(default=0)
    source_trafic = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        db_table = 'fact_session_navigation'
        verbose_name = 'Session de navigation'
        verbose_name_plural = 'Sessions de navigation'


class EvenementComportemental(models.Model):
    """Événements comportementaux"""
    TYPES_EVENEMENT = [
        ('vue_produit', 'Vue Produit'),
        ('ajout_panier', 'Ajout Panier'),
        ('abandon_panier', 'Abandon Panier'),
        ('achat', 'Achat'),
        ('recherche', 'Recherche'),
        ('favori', 'Ajout Favori'),
    ]

    id_evenement = models.AutoField(primary_key=True)
    session = models.ForeignKey(SessionNavigation, on_delete=models.CASCADE, related_name='evenements')
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True, related_name='evenements')
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, null=True, blank=True, related_name='evenements')
    type_evenement = models.CharField(max_length=20, choices=TYPES_EVENEMENT)
    timestamp = models.DateTimeField(auto_now_add=True)
    url_page = models.URLField(blank=True, null=True)
    duree_engagement = models.IntegerField(default=0)

    class Meta:
        db_table = 'fact_evenement_comportemental'
        verbose_name = 'Événement comportemental'
        verbose_name_plural = 'Événements comportementaux'
        indexes = [
            models.Index(fields=['type_evenement', 'timestamp']),
            models.Index(fields=['produit', 'type_evenement']),
            models.Index(fields=['client', 'timestamp']),
        ]


# ═════════════════════════════════════════════
# CHATBOT (§4.3)
# ═════════════════════════════════════════════

class IntentChatbot(models.Model):
    """Corpus d'entraînement pour le chatbot NLP"""
    INTENTS = [
        ('kpi_request', 'Demande de KPI'),
        ('comparison_request', 'Demande de comparaison'),
        ('trend_request', 'Demande de tendance'),
        ('anomaly_request', 'Détection d\'anomalie'),
        ('product_request', 'Info produit'),
        ('category_request', 'Info catégorie'),
        ('greeting', 'Salutation'),
        ('fallback', 'Fallback'),
    ]

    id_intent = models.AutoField(primary_key=True)
    phrase = models.TextField()
    intent = models.CharField(max_length=20, choices=INTENTS)
    langue = models.CharField(max_length=10, default='fr')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'dim_intent_chatbot'
        verbose_name = 'Intention Chatbot'
        verbose_name_plural = 'Intentions Chatbot'
        unique_together = ['phrase', 'intent']

    def __str__(self):
        return f"{self.intent}: {self.phrase[:50]}..."


class ConversationChatbot(models.Model):
    """Historique des conversations"""
    id_conversation = models.AutoField(primary_key=True)
    session_id = models.UUIDField(default=uuid.uuid4)
    user_message = models.TextField()
    intent_detecte = models.CharField(max_length=20, blank=True, null=True)
    confiance = models.FloatField(default=0)
    reponse = models.TextField()
    sql_genere = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'fact_conversation_chatbot'
        verbose_name = 'Conversation Chatbot'
        verbose_name_plural = 'Conversations Chatbot'
        ordering = ['-timestamp']


# ═════════════════════════════════════════════
# SYSTÈME DE KPIs CONFIGURABLE (Nouveau)
# ═════════════════════════════════════════════

class IndicateurPersonnalise(models.Model):
    """
    KPI configurable par l'utilisateur.
    L'utilisateur crée ses indicateurs, le système génère le canevas et le dashboard.
    """
    TYPES_CALCUL = [
        ('somme', 'Somme'),
        ('moyenne', 'Moyenne'),
        ('compte', 'Compte distinct'),
        ('formule', 'Formule personnalisée'),
        ('ratio', 'Ratio entre 2 champs'),
        ('pourcentage', 'Pourcentage de variation'),
        ('min', 'Minimum'),
        ('max', 'Maximum'),
    ]

    TYPES_AFFICHAGE = [
        ('nombre', 'Nombre'),
        ('montant', 'Montant (DZD)'),
        ('pourcentage', 'Pourcentage'),
        ('duree', 'Durée (jours)'),
        ('texte', 'Texte'),
    ]

    id_indicateur = models.AutoField(primary_key=True)
    code = models.CharField(max_length=50, unique=True)
    nom = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    type_calcul = models.CharField(max_length=20, choices=TYPES_CALCUL, default='somme')
    type_affichage = models.CharField(max_length=20, choices=TYPES_AFFICHAGE, default='montant')

    # Configuration du calcul
    champ_source = models.CharField(max_length=100, blank=True, help_text="Champ de la table source (ex: ca_ligne)")
    table_source = models.CharField(max_length=100, default='fait_ligne_commande')
    formule = models.TextField(blank=True, help_text="Formule SQL ou expression Python (si type=formule)")

    # Pour les ratios
    champ_numerateur = models.CharField(max_length=100, blank=True)
    champ_denominateur = models.CharField(max_length=100, blank=True)

    # Seuils d'alerte
    seuil_alerte_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    seuil_alerte_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    couleur_positive = models.CharField(max_length=7, default='#22c55e')
    couleur_negative = models.CharField(max_length=7, default='#ef4444')

    # Affichage dashboard
    ordre_affichage = models.IntegerField(default=0)
    visible = models.BooleanField(default=True)
    icone = models.CharField(max_length=50, default='fa-chart-line')

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='indicateurs_crees')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'config_indicateur'
        verbose_name = 'Indicateur personnalisé'
        verbose_name_plural = 'Indicateurs personnalisés'
        ordering = ['ordre_affichage', 'nom']

    def __str__(self):
        return f"{self.code} - {self.nom}"


class DimensionAnalyse(models.Model):
    """
    Dimensions configurables pour les analyses (drill-down).
    """
    id_dimension = models.AutoField(primary_key=True)
    code = models.CharField(max_length=50, unique=True)
    nom = models.CharField(max_length=100)
    champ_sql = models.CharField(max_length=200, help_text="Expression SQL ou champ modèle (ex: commande__client__region)")
    table_source = models.CharField(max_length=100)
    ordre = models.IntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        db_table = 'config_dimension'
        verbose_name = 'Dimension d\'analyse'
        verbose_name_plural = 'Dimensions d\'analyse'
        ordering = ['ordre']

    def __str__(self):
        return self.nom


class WidgetDashboard(models.Model):
    """
    Widgets du dashboard créés dynamiquement selon les KPIs configurés.
    """
    TYPES_WIDGET = [
        ('kpi_card', 'Carte KPI'),
        ('line_chart', 'Graphique ligne'),
        ('bar_chart', 'Graphique barres'),
        ('pie_chart', 'Graphique circulaire'),
        ('table', 'Tableau de données'),
        ('funnel', 'Entonnoir'),
        ('gauge', 'Jauge'),
        ('heatmap', 'Carte de chaleur'),
    ]

    id_widget = models.AutoField(primary_key=True)
    nom = models.CharField(max_length=200)
    type_widget = models.CharField(max_length=20, choices=TYPES_WIDGET)
    indicateur = models.ForeignKey(IndicateurPersonnalise, on_delete=models.CASCADE, related_name='widgets')
    dimensions = models.ManyToManyField(DimensionAnalyse, blank=True)

    # Position et taille (grid layout)
    position_x = models.IntegerField(default=0)
    position_y = models.IntegerField(default=0)
    largeur = models.IntegerField(default=6)
    hauteur = models.IntegerField(default=4)

    # Filtres par défaut
    filtre_periode = models.CharField(max_length=20, blank=True)
    filtre_region = models.CharField(max_length=100, blank=True)

    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'config_widget'
        verbose_name = 'Widget Dashboard'
        verbose_name_plural = 'Widgets Dashboard'


class ConfigurationProjet(models.Model):
    """
    Configuration globale du projet par utilisateur/entreprise.
    Définit la structure du canevas de saisie.
    """
    id_config = models.AutoField(primary_key=True)
    nom_projet = models.CharField(max_length=200, default='Mon Dashboard')
    description = models.TextField(blank=True)

    # Colonnes du canevas de saisie (JSON schema)
    colonnes_canevas = models.JSONField(
        default=dict,
        help_text="Structure JSON des colonnes attendues: [{nom, type, obligatoire, description}]"
    )

    # Thème
    theme_couleur = models.CharField(max_length=7, default='#f97316')
    logo_url = models.URLField(blank=True)

    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'config_projet'
        verbose_name = 'Configuration projet'
        verbose_name_plural = 'Configurations projet'

    def __str__(self):
        return self.nom_projet


class DonneeBrute(models.Model):
    """
    Données brutes importées par l'utilisateur (ligne par ligne).
    Structure flexible selon le canevas configuré.
    """
    id_donnee = models.AutoField(primary_key=True)
    config = models.ForeignKey(ConfigurationProjet, on_delete=models.CASCADE, related_name='donnees')

    # Champs de base (toujours présents)
    date_transaction = models.DateField()
    code_client = models.CharField(max_length=50)
    nom_client = models.CharField(max_length=200, blank=True)
    region = models.CharField(max_length=100, blank=True)
    code_article = models.CharField(max_length=50)
    nom_article = models.CharField(max_length=200, blank=True)
    categorie = models.CharField(max_length=100, blank=True)
    code_commercial = models.CharField(max_length=50, blank=True)
    nom_commercial = models.CharField(max_length=200, blank=True)
    quantite = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    prix_unitaire = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remise = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Champs personnalisés (JSON pour flexibilité)
    champs_personnalises = models.JSONField(default=dict, blank=True)

    # Calculés automatiquement
    ca_ligne = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    marge_ligne = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'donnee_brute'
        verbose_name = 'Donnée brute'
        verbose_name_plural = 'Données brutes'
        indexes = [
            models.Index(fields=['config', 'date_transaction']),
            models.Index(fields=['code_client']),
            models.Index(fields=['code_article']),
        ]

    def save(self, *args, **kwargs):
        self.ca_ligne = self.quantite * self.prix_unitaire * (1 - self.remise / 100)
        super().save(*args, **kwargs)


# ═════════════════════════════════════════════
# CONFIGURATION SYSTÈME
# ═════════════════════════════════════════════

class ParametreSysteme(models.Model):
    """Paramètres configurables du système"""
    cle = models.CharField(max_length=100, primary_key=True)
    valeur = models.TextField()
    description = models.TextField(blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'parametre_systeme'
        verbose_name = 'Paramètre Système'
        verbose_name_plural = 'Paramètres Système'

    def __str__(self):
        return f"{self.cle}: {self.valeur[:50]}"
