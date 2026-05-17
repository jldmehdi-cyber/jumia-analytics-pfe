from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('configurator/', views.configurator, name='configurator'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # API Auth
    path('api/auth/login/', views.api_login, name='api_login'),
    path('api/health/', views.health_check, name='health_check'),
    
    # API KPIs
    path('api/kpis/', views.api_kpis, name='api_kpis'),
    path('api/tendances/', views.api_tendances, name='api_tendances'),
    path('api/rfm/', views.api_rfm, name='api_rfm'),
    path('api/par-region/', views.api_par_region, name='api_par_region'),
    path('api/par-article/', views.api_par_article, name='api_par_article'),
    path('api/funnel/', views.api_funnel, name='api_funnel'),
    path('api/produits-fantomes/', views.api_produits_fantomes, name='api_produits_fantomes'),
    path('api/produits-caches/', views.api_produits_caches, name='api_produits_caches'),
    path('api/points-friction/', views.api_points_friction, name='api_points_friction'),
    path('api/segmentation-comportementale/', views.api_segmentation_comportementale, name='api_segmentation_comportementale'),
    
    # API Chatbot
    path('api/chatbot/', views.api_chatbot, name='api_chatbot'),
    path('api/chatbot/history/', views.api_chatbot_history, name='api_chatbot_history'),
    
    # API Previsions
    path('api/previsions/', views.api_previsions, name='api_previsions'),
    path('api/alertes/', views.api_alertes, name='api_alertes'),
    path('api/recommandations/', views.api_recommandations, name='api_recommandations'),
    
    # API Exports
    path('api/export/excel/', views.api_export_excel, name='api_export_excel'),
    path('api/export/csv/', views.api_export_csv, name='api_export_csv'),
    
    # API Import
    path('api/import/', views.api_import_excel, name='api_import_excel'),

    # API Canevas libre (sans configuration préalable)
    path('api/canevas/generer/', views.api_generer_canevas_libre, name='api_generer_canevas_libre'),
    
    # API Indicateurs
    path('api/indicateurs/', views.api_indicateurs, name='api_indicateurs'),
    path('api/indicateurs/<int:pk>/', views.api_indicateur_detail, name='api_indicateur_detail'),
    path('api/indicateurs/<int:pk>/calculer/', views.api_calculer_kpi, name='api_calculer_kpi'),
    path('api/indicateurs/<int:pk>/par-dimension/', views.api_kpi_par_dimension, name='api_kpi_par_dimension'),

    # API KPIs personnalisés dashboard
    path('api/kpis-personnalises/', views.api_kpis_personnalises, name='api_kpis_personnalises'),
    path('api/colonnes/', views.api_colonnes_disponibles, name='api_colonnes_disponibles'),
    
    # API Configurations
    path('api/configurations/', views.api_configurations, name='api_configurations'),
    path('api/configurations/<int:pk>/', views.api_configuration_detail, name='api_configuration_detail'),
    path('api/configurations/<int:pk>/canevas/', views.api_generer_canevas, name='api_generer_canevas'),
    path('api/configurations/<int:pk>/importer/', views.api_importer_canevas, name='api_importer_canevas'),
    
    # API Widgets
    path('api/widgets/', views.api_widgets, name='api_widgets'),
    path('api/dashboard-dynamique/', views.api_dashboard_dynamique, name='api_dashboard_dynamique'),

    # Import admin
    path('api/admin/import-etat/', views.import_etat_data, name='import_etat_data'),
]