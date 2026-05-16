"""
URL configuration for jumia_analytics project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static
from django.conf import settings


def _setup_railway(request):
    """Import lazy pour éviter les problèmes de chargement de module."""
    from analytics.views import setup_railway
    return setup_railway(request)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('analytics.urls')),
    path('setup/', _setup_railway, name='setup'),
    path('', include('analytics.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
