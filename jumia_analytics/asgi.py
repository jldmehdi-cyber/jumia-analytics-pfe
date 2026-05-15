"""
ASGI config for jumia_analytics project.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'jumia_analytics.settings')

application = get_asgi_application()
