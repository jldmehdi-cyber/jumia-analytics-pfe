"""
Middleware pour le logging des requêtes et collecte comportementale.
Aligné avec le mémoire §4.2 : traces hétérogènes de navigation.
"""
import time
import logging
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger('analytics')


class RequestLoggingMiddleware(MiddlewareMixin):
    """Log chaque requête API pour analyse comportementale"""

    def process_request(self, request):
        request.start_time = time.time()
        return None

    def process_response(self, request, response):
        duration = time.time() - getattr(request, 'start_time', 0)

        # Log structuré
        logger.info(
            f"API_CALL | {request.method} {request.path} | "
            f"Status: {response.status_code} | "
            f"Duration: {duration:.3f}s | "
            f"User: {request.user if request.user.is_authenticated else 'anonymous'} | "
            f"IP: {self.get_client_ip(request)}"
        )

        return response

    @staticmethod
    def get_client_ip(request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
