"""
Configuration de l'application analytics.
"""
from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics'
    verbose_name = 'Analytics'

    def ready(self):
        """Initialisation au démarrage de Django"""
        pass
