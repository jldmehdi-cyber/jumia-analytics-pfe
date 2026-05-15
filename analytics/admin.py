"""
Configuration Django Admin pour le dashboard analytique.
Inclut les modèles configurables (KPIs, Dimensions, Widgets).
"""
from django.contrib import admin
from .models import (
    Client, Produit, Categorie, Commercial, Commande, LigneCommande,
    SessionNavigation, EvenementComportemental, IntentChatbot,
    ConversationChatbot, ParametreSysteme,
    # Modèles configurables
    IndicateurPersonnalise, DimensionAnalyse, WidgetDashboard,
    ConfigurationProjet, DonneeBrute
)


@admin.register(Categorie)
class CategorieAdmin(admin.ModelAdmin):
    list_display = ['id_categorie', 'nom_categorie', 'description']
    search_fields = ['nom_categorie']


@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ['code_article', 'nom_article', 'categorie', 'prix_unitaire', 'stock_disponible', 'marge']
    list_filter = ['categorie']
    search_fields = ['code_article', 'nom_article']


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['code_client', 'nom_client', 'region', 'segment_rfm', 'score_rfm', 'frequence', 'montant']
    list_filter = ['segment_rfm', 'region']
    search_fields = ['code_client', 'nom_client']


@admin.register(Commercial)
class CommercialAdmin(admin.ModelAdmin):
    list_display = ['code_commercial', 'nom_commercial', 'zone']
    search_fields = ['nom_commercial']


@admin.register(Commande)
class CommandeAdmin(admin.ModelAdmin):
    list_display = ['numero_commande', 'client', 'commercial', 'date_commande', 'total_ht', 'total_ttc']
    list_filter = ['date_commande', 'annee', 'mois']
    date_hierarchy = 'date_commande'


@admin.register(LigneCommande)
class LigneCommandeAdmin(admin.ModelAdmin):
    list_display = ['commande', 'produit', 'quantite', 'prix_unitaire', 'ca_ligne', 'marge_ligne']
    list_filter = ['produit__categorie']


@admin.register(SessionNavigation)
class SessionNavigationAdmin(admin.ModelAdmin):
    list_display = ['id_session', 'client', 'source_trafic', 'date_debut', 'duree_secondes']
    list_filter = ['source_trafic', 'date_debut']


@admin.register(EvenementComportemental)
class EvenementComportementalAdmin(admin.ModelAdmin):
    list_display = ['id_evenement', 'type_evenement', 'client', 'produit', 'timestamp']
    list_filter = ['type_evenement', 'timestamp']


@admin.register(IntentChatbot)
class IntentChatbotAdmin(admin.ModelAdmin):
    list_display = ['phrase', 'intent', 'langue']
    list_filter = ['intent']
    search_fields = ['phrase']


@admin.register(ConversationChatbot)
class ConversationChatbotAdmin(admin.ModelAdmin):
    list_display = ['id_conversation', 'intent_detecte', 'confiance', 'timestamp']
    list_filter = ['intent_detecte', 'timestamp']


@admin.register(ParametreSysteme)
class ParametreSystemeAdmin(admin.ModelAdmin):
    list_display = ['cle', 'valeur', 'updated_at']


# ═════════════════════════════════════════════
# ADMIN DES MODÈLES CONFIGURABLES
# ═════════════════════════════════════════════

@admin.register(IndicateurPersonnalise)
class IndicateurPersonnaliseAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom', 'type_calcul', 'type_affichage', 'champ_source', 'visible', 'ordre_affichage']
    list_filter = ['type_calcul', 'type_affichage', 'visible']
    search_fields = ['code', 'nom', 'description']
    list_editable = ['ordre_affichage', 'visible']
    fieldsets = (
        ('Informations générales', {
            'fields': ('code', 'nom', 'description', 'icone')
        }),
        ('Configuration du calcul', {
            'fields': ('type_calcul', 'champ_source', 'table_source', 'formule', 'champ_numerateur', 'champ_denominateur')
        }),
        ('Affichage', {
            'fields': ('type_affichage', 'ordre_affichage', 'visible')
        }),
        ('Alertes', {
            'fields': ('seuil_alerte_min', 'seuil_alerte_max', 'couleur_positive', 'couleur_negative')
        }),
    )


@admin.register(DimensionAnalyse)
class DimensionAnalyseAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom', 'champ_sql', 'table_source', 'active']
    list_filter = ['active']
    list_editable = ['active']


@admin.register(WidgetDashboard)
class WidgetDashboardAdmin(admin.ModelAdmin):
    list_display = ['nom', 'type_widget', 'indicateur', 'position_x', 'position_y', 'largeur', 'hauteur']
    list_filter = ['type_widget']
    filter_horizontal = ['dimensions']


@admin.register(ConfigurationProjet)
class ConfigurationProjetAdmin(admin.ModelAdmin):
    list_display = ['nom_projet', 'created_by', 'created_at', 'updated_at']
    search_fields = ['nom_projet']


@admin.register(DonneeBrute)
class DonneeBruteAdmin(admin.ModelAdmin):
    list_display = ['config', 'date_transaction', 'code_client', 'code_article', 'ca_ligne', 'marge_ligne']
    list_filter = ['config', 'date_transaction']
    search_fields = ['code_client', 'code_article']
