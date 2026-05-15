"""
URL configuration for jumia_analytics project.
"""
from django.contrib import admin
from django.urls import path, include
from analytics.views import setup_railway  # ← AJOUTER CETTE IMPORTATION

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('analytics.urls')),
    path('setup/', setup_railway, name='setup'),  # ← AJOUTER CETTE LIGNE
    path('', include('analytics.urls')),
]
# Servir les fichiers statiques en développement
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
