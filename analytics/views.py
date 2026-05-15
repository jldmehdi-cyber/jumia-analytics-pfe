"""
Vues API REST alignées avec le mémoire PFE.
Endpoints pour KPIs, données comportementales, chatbot, exports.
"""
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import connection
from django.db.models import Sum, Avg, Count, F, Q, Max, Min
from django.db.models.functions import TruncMonth, TruncQuarter
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    IndicateurPersonnalise, DimensionAnalyse, WidgetDashboard, ConfigurationProjet, DonneeBrute,
    Client, Produit, Categorie, Commercial, Commande, LigneCommande,
    SessionNavigation, EvenementComportemental, ConversationChatbot,
    ParametreSysteme, IntentChatbot
)
from .chatbot_engine import get_chatbot

logger = logging.getLogger('analytics')


# ─────────────────────────────────────────────
# AUTHENTIFICATION
# ─────────────────────────────────────────────

class CustomTokenObtainPairView(TokenObtainPairView):
    """Login JWT personnalisé"""
    pass


@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    """Endpoint de connexion (fallback si TokenObtainPairView non utilisé)"""
    username = request.data.get('username')
    password = request.data.get('password')

    from django.contrib.auth import authenticate
    user = authenticate(username=username, password=password)

    if user:
        refresh = RefreshToken.for_user(user)
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {'username': user.username, 'email': user.email}
        })

    return Response({'error': 'Identifiants invalides'}, status=status.HTTP_401_UNAUTHORIZED)


# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """Vérification santé du système"""
    return Response({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'version': '2.1.0',
        'database': 'connected' if check_db() else 'error'
    })


def check_db():
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except:
        return False


# ─────────────────────────────────────────────
# KPIs PRINCIPAUX (§4.1.1)
# ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_kpis(request):
    """KPIs globaux avec filtre période/région"""
    region = request.GET.get('region', 'all')
    periode = request.GET.get('periode', 'all')  # all, mois, trimestre, annee

    # Filtre de base
    qs = LigneCommande.objects.select_related('commande', 'produit')

    if region != 'all':
        qs = qs.filter(commande__client__region=region)

    if periode == 'mois':
        qs = qs.filter(commande__date_commande__gte=datetime.now() - timedelta(days=30))
    elif periode == 'trimestre':
        qs = qs.filter(commande__date_commande__gte=datetime.now() - timedelta(days=90))
    elif periode == 'annee':
        qs = qs.filter(commande__date_commande__gte=datetime.now() - timedelta(days=365))

    # Agrégations
    total_ca = qs.aggregate(total=Sum('ca_ligne'))['total'] or 0
    total_marge = qs.aggregate(total=Sum('marge_ligne'))['total'] or 0
    nb_commandes = qs.values('commande').distinct().count()
    nb_clients = qs.values('commande__client').distinct().count()

    panier_moyen = (total_ca / nb_commandes) if nb_commandes > 0 else 0
    marge_pct = (total_marge / total_ca * 100) if total_ca > 0 else 0

    # Période précédente pour comparaison
    if periode == 'mois':
        prev_start = datetime.now() - timedelta(days=60)
        prev_end = datetime.now() - timedelta(days=30)
    elif periode == 'trimestre':
        prev_start = datetime.now() - timedelta(days=180)
        prev_end = datetime.now() - timedelta(days=90)
    elif periode == 'annee':
        prev_start = datetime.now() - timedelta(days=730)
        prev_end = datetime.now() - timedelta(days=365)
    else:
        prev_start = None

    growth = 0
    if prev_start:
        prev_qs = LigneCommande.objects.filter(
            commande__date_commande__gte=prev_start,
            commande__date_commande__lt=prev_end
        )
        if region != 'all':
            prev_qs = prev_qs.filter(commande__client__region=region)
        prev_ca = prev_qs.aggregate(total=Sum('ca_ligne'))['total'] or 0
        growth = round((total_ca - prev_ca) / prev_ca * 100, 1) if prev_ca > 0 else 0

    return Response({
        'chiffre_affaires': float(total_ca),
        'marge_totale': float(total_marge),
        'marge_pourcentage': round(float(marge_pct), 1),
        'nombre_commandes': nb_commandes,
        'nombre_clients': nb_clients,
        'panier_moyen': round(float(panier_moyen), 2),
        'croissance': growth,
        'periode': periode,
        'region': region
    })


# ─────────────────────────────────────────────
# ANALYSE TEMPORELLE (§4.1.2)
# ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_tendances(request):
    """Évolution temporelle CA/marge par mois"""
    region = request.GET.get('region', 'all')
    annee = request.GET.get('annee')

    qs = LigneCommande.objects.select_related('commande')

    if region != 'all':
        qs = qs.filter(commande__client__region=region)
    if annee:
        qs = qs.filter(commande__annee=int(annee))

    data = qs.annotate(
        mois_label=F('commande__mois'),
        annee_label=F('commande__annee')
    ).values('annee_label', 'mois_label').annotate(
        ca=Sum('ca_ligne'),
        marge=Sum('marge_ligne'),
        nb_commandes=Count('commande', distinct=True)
    ).order_by('annee_label', 'mois_label')

    return Response({
        'labels': [f"{d['annee_label']}-{d['mois_label']:02d}" for d in data],
        'ca': [float(d['ca'] or 0) for d in data],
        'marge': [float(d['marge'] or 0) for d in data],
        'commandes': [d['nb_commandes'] for d in data]
    })


# ─────────────────────────────────────────────
# SEGMENTATION RFM (§4.1.3)
# ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_rfm(request):
    """Analyse RFM des clients"""
    # Recalcul RFM si demandé
    recalculer = request.GET.get('recalculer', 'false').lower() == 'true'

    if recalculer:
        _recalculer_rfm()

    segments = Client.objects.values('segment_rfm').annotate(
        count=Count('id_client'),
        ca_moyen=Avg('montant')
    ).order_by('-count')

    top_clients = Client.objects.order_by('-score_rfm')[:10].values(
        'nom_client', 'segment_rfm', 'recence', 'frequence', 
        'montant', 'score_rfm', 'ville'
    )

    return Response({
        'segments': [
            {
                'segment': s['segment_rfm'],
                'count': s['count'],
                'ca_moyen': float(s['ca_moyen'] or 0)
            }
            for s in segments
        ],
        'top_clients': list(top_clients)
    })


def _recalculer_rfm():
    """Recalcule les scores RFM pour tous les clients"""
    from django.db.models import Max

    date_ref = Commande.objects.aggregate(max_date=Max('date_commande'))['max_date']
    if not date_ref:
        return

    clients = Client.objects.all()
    for client in clients:
        commandes = Commande.objects.filter(client=client)

        if not commandes.exists():
            continue

        # Recence
        derniere_cmd = commandes.order_by('-date_commande').first()
        recence = (date_ref - derniere_cmd.date_commande).days

        # Frequence
        frequence = commandes.count()

        # Montant
        montant = LigneCommande.objects.filter(
            commande__client=client
        ).aggregate(total=Sum('ca_ligne'))['total'] or 0

        # Scores (1-5)
        r_score = max(1, 5 - recence // 30)  # Plus récent = meilleur
        f_score = min(5, frequence)
        m_score = min(5, int(montant / 10000) + 1)

        score_rfm = r_score * 100 + f_score * 10 + m_score

        # Segmentation
        if r_score >= 4 and f_score >= 4:
            segment = 'champions'
        elif r_score >= 3 and f_score >= 3:
            segment = 'clients_fideles'
        elif r_score >= 4 and f_score <= 2:
            segment = 'clients_potentiels'
        elif r_score >= 4 and f_score == 1:
            segment = 'nouveaux'
        elif r_score <= 2 and f_score >= 3:
            segment = 'clients_perdus'
        else:
            segment = 'hibernation'

        client.recence = recence
        client.frequence = frequence
        client.montant = montant
        client.score_rfm = score_rfm
        client.segment_rfm = segment
        client.save()


# ─────────────────────────────────────────────
# ANALYSE PAR RÉGION/ARTICLE (§4.1)
# ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_par_region(request):
    """Analyse des ventes par région"""
    data = LigneCommande.objects.select_related(
        'commande__client'
    ).values('commande__client__region').annotate(
        ca=Sum('ca_ligne'),
        marge=Sum('marge_ligne'),
        nb_commandes=Count('commande', distinct=True),
        nb_clients=Count('commande__client', distinct=True)
    ).order_by('-ca')

    return Response({
        'regions': [
            {
                'region': d['commande__client__region'] or 'Non spécifié',
                'ca': float(d['ca'] or 0),
                'marge': float(d['marge'] or 0),
                'commandes': d['nb_commandes'],
                'clients': d['nb_clients']
            }
            for d in data
        ]
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_par_article(request):
    """Analyse des ventes par article"""
    top_n = int(request.GET.get('top', 20))

    data = LigneCommande.objects.select_related('produit').values(
        'produit__code_article', 'produit__nom_article'
    ).annotate(
        ca=Sum('ca_ligne'),
        quantite=Sum('quantite'),
        marge=Sum('marge_ligne')
    ).order_by('-ca')[:top_n]

    return Response({
        'articles': [
            {
                'code': d['produit__code_article'],
                'nom': d['produit__nom_article'],
                'ca': float(d['ca'] or 0),
                'quantite': d['quantite'],
                'marge': float(d['marge'] or 0)
            }
            for d in data
        ]
    })


# ─────────────────────────────────────────────
# DONNÉES COMPORTEMENTALES (§4.2)
# ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_funnel(request):
    """Funnel de conversion (§4.2.2)"""
    # Compte les événements par type
    events = EvenementComportemental.objects.values('type_evenement').annotate(
        count=Count('id_evenement')
    )

    event_map = {e['type_evenement']: e['count'] for e in events}

    vues = event_map.get('vue_produit', 0)
    ajouts = event_map.get('ajout_panier', 0)
    achats = event_map.get('achat', 0)

    # Taux de conversion
    taux_panier = round(ajouts / vues * 100, 2) if vues > 0 else 0
    taux_achat = round(achats / ajouts * 100, 2) if ajouts > 0 else 0
    taux_global = round(achats / vues * 100, 2) if vues > 0 else 0

    return Response({
        'funnel': [
            {'etape': 'Vues Produit', 'count': vues, 'taux': 100.0},
            {'etape': 'Ajouts Panier', 'count': ajouts, 'taux': taux_panier},
            {'etape': 'Achats', 'count': achats, 'taux': taux_achat},
        ],
        'taux_conversion_global': taux_global,
        'taux_abandon': round(100 - taux_panier, 2) if vues > 0 else 0
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_produits_fantomes(request):
    """Produits fantômes : vues élevées, achats faibles (§4.2.3)"""
    # Ratio vue/achat > 50:1
    fantomes = []

    for produit in Produit.objects.all():
        vues = EvenementComportemental.objects.filter(
            produit=produit, type_evenement='vue_produit'
        ).count()
        achats = LigneCommande.objects.filter(produit=produit).aggregate(
            total=Sum('quantite')
        )['total'] or 0

        if vues > 0 and achats > 0 and vues / achats > 50:
            fantomes.append({
                'code': produit.code_article,
                'nom': produit.nom_article,
                'vues': vues,
                'achats': int(achats),
                'ratio': round(vues / achats, 1),
                'prix': float(produit.prix_unitaire)
            })

    fantomes.sort(key=lambda x: x['ratio'], reverse=True)
    return Response({'produits_fantomes': fantomes[:20]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_produits_caches(request):
    """Produits cachés : faibles vues, haute conversion (§4.2.4)"""
    caches = []

    for produit in Produit.objects.all():
        vues = EvenementComportemental.objects.filter(
            produit=produit, type_evenement='vue_produit'
        ).count()
        achats = LigneCommande.objects.filter(produit=produit).aggregate(
            total=Sum('quantite')
        )['total'] or 0

        if vues > 10 and achats > 0 and vues / achats < 5:
            caches.append({
                'code': produit.code_article,
                'nom': produit.nom_article,
                'vues': vues,
                'achats': int(achats),
                'ratio': round(vues / achats, 1),
                'ca': float(LigneCommande.objects.filter(produit=produit).aggregate(
                    total=Sum('ca_ligne')
                )['total'] or 0)
            })

    caches.sort(key=lambda x: x['ratio'])
    return Response({'produits_caches': caches[:20]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_points_friction(request):
    """Points de friction : abandons de panier (§4.2.5)"""
    # Pages avec plus d'abandons que d'achats
    abandons = EvenementComportemental.objects.filter(
        type_evenement='abandon_panier'
    ).values('url_page').annotate(count=Count('id_evenement')).order_by('-count')[:10]

    return Response({
        'points_friction': [
            {
                'page': a['url_page'] or 'Page inconnue',
                'abandons': a['count']
            }
            for a in abandons
        ]
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_segmentation_comportementale(request):
    """Segmentation comportementale (§4.2.6)"""
    # Segments basés sur le comportement de navigation
    segments = {}

    for client in Client.objects.all():
        events = EvenementComportemental.objects.filter(client=client)
        vues = events.filter(type_evenement='vue_produit').count()
        ajouts = events.filter(type_evenement='ajout_panier').count()
        achats = events.filter(type_evenement='achat').count()

        if achats > 5:
            segment = 'acheteurs_frequents'
        elif ajouts > 10 and achats == 0:
            segment = 'panier_abandonneur'
        elif vues > 50 and achats == 0:
            segment = 'curieux_indecis'
        elif vues > 0 and achats > 0:
            segment = 'acheteur_occasionnel'
        else:
            segment = 'inactif'

        segments[segment] = segments.get(segment, 0) + 1

    return Response({
        'segmentation': [
            {'segment': k, 'count': v}
            for k, v in sorted(segments.items(), key=lambda x: -x[1])
        ]
    })


# ─────────────────────────────────────────────
# CHATBOT (§4.3)
# ─────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_chatbot(request):
    """Endpoint chatbot : reçoit message, retourne réponse + SQL"""
    message = request.data.get('message', '').strip()
    session_id = request.data.get('session_id')

    if not message:
        return Response({'error': 'Message vide'}, status=400)

    try:
        chatbot = get_chatbot()

        # Prédiction
        intent_data = chatbot.predict_intent(message)
        response_data = chatbot.generate_response(message, intent_data)

        # Sauvegarde conversation
        ConversationChatbot.objects.create(
            session_id=session_id or None,
            user_message=message,
            intent_detecte=intent_data['intent'],
            confiance=intent_data['confidence'],
            reponse=response_data['text'],
            sql_genere=response_data.get('sql_template')
        )

        return Response({
            'message': message,
            'intent': intent_data['intent'],
            'confidence': intent_data['confidence'],
            'response': response_data['text'],
            'sql_template': response_data.get('sql_template'),
            'viz_type': response_data.get('viz_type', 'text'),
            'all_probs': intent_data['all_probs']
        })

    except Exception as e:
        logger.error(f"Chatbot error: {e}")
        return Response({
            'error': 'Erreur interne du chatbot',
            'response': "Désolé, une erreur s'est produite. Veuillez réessayer."
        }, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_chatbot_history(request):
    """Historique des conversations"""
    limit = int(request.GET.get('limit', 50))
    conversations = ConversationChatbot.objects.all().order_by('-timestamp')[:limit]

    return Response({
        'conversations': [
            {
                'id': c.id_conversation,
                'message': c.user_message,
                'intent': c.intent_detecte,
                'confidence': c.confiance,
                'response': c.reponse,
                'timestamp': c.timestamp.isoformat()
            }
            for c in conversations
        ]
    })


# ─────────────────────────────────────────────
# PRÉVISIONS ML
# ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_previsions(request):
    """Prévisions de ventes par régression polynomiale"""
    from sklearn.preprocessing import PolynomialFeatures
    from sklearn.linear_model import LinearRegression
    import numpy as np

    # Données mensuelles
    data = LigneCommande.objects.select_related('commande').annotate(
        mois=F('commande__mois'),
        annee=F('commande__annee')
    ).values('annee', 'mois').annotate(
        ca=Sum('ca_ligne')
    ).order_by('annee', 'mois')

    if len(data) < 6:
        return Response({'error': 'Pas assez de données historiques (minimum 6 mois)'}, status=400)

    # Préparation données
    X = np.array([[i] for i in range(len(data))])
    y = np.array([float(d['ca'] or 0) for d in data])

    # Régression polynomiale degré 2
    poly = PolynomialFeatures(degree=2)
    X_poly = poly.fit_transform(X)

    model = LinearRegression()
    model.fit(X_poly, y)

    # Prédictions sur 3 mois
    future_months = 3
    predictions = []

    for i in range(future_months):
        pred = model.predict(poly.transform([[len(data) + i]]))[0]
        predictions.append({
            'mois': f"M+{i+1}",
            'prediction': max(0, round(float(pred), 2))
        })

    return Response({
        'historique': {
            'labels': [f"{d['annee']}-{d['mois']:02d}" for d in data],
            'ca': [float(d['ca'] or 0) for d in data]
        },
        'previsions': predictions,
        'r2_score': round(model.score(X_poly, y), 3)
    })


# ─────────────────────────────────────────────
# ALERTES & ANOMALIES
# ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_alertes(request):
    """Alertes automatiques basées sur Isolation Forest"""
    from sklearn.ensemble import IsolationForest
    import numpy as np

    # Données mensuelles par commercial
    data = LigneCommande.objects.select_related(
        'commande__commercial'
    ).values('commande__commercial__nom_commercial').annotate(
        ca=Sum('ca_ligne'),
        nb_cmd=Count('commande', distinct=True)
    ).order_by('-ca')

    if len(data) < 3:
        return Response({'alertes': []})

    # Détection d'anomalies
    X = np.array([[float(d['ca'] or 0), d['nb_cmd']] for d in data])

    clf = IsolationForest(contamination=0.2, random_state=42)
    predictions = clf.fit_predict(X)

    alertes = []
    for i, d in enumerate(data):
        if predictions[i] == -1:
            alertes.append({
                'type': 'anomalie_commercial',
                'commercial': d['commande__commercial__nom_commercial'] or 'Non assigné',
                'ca': float(d['ca'] or 0),
                'nb_commandes': d['nb_cmd'],
                'severite': 'haute' if float(d['ca'] or 0) < np.median(X[:, 0]) else 'moyenne',
                'message': f"Performance anormale détectée pour {d['commande__commercial__nom_commercial']}"
            })

    return Response({'alertes': alertes})


# ─────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_export_excel(request):
    """Export des données en Excel"""
    import pandas as pd
    from io import BytesIO

    # Récupérer les données
    data = LigneCommande.objects.select_related(
        'commande__client', 'commande__commercial', 'produit__categorie'
    ).values(
        'commande__numero_commande',
        'commande__date_commande',
        'commande__client__nom_client',
        'commande__client__region',
        'commande__commercial__nom_commercial',
        'produit__code_article',
        'produit__nom_article',
        'produit__categorie__nom_categorie',
        'quantite',
        'prix_unitaire',
        'ca_ligne',
        'marge_ligne'
    )

    df = pd.DataFrame(list(data))

    # Renommer colonnes
    df.columns = [
        'N° Commande', 'Date', 'Client', 'Région', 'Commercial',
        'Code Article', 'Article', 'Catégorie', 'Qté', 'Prix Unitaire',
        'CA Ligne', 'Marge Ligne'
    ]

    # Export Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Données', index=False)

        # Résumé
        resume = pd.DataFrame({
            'Métrique': ['CA Total', 'Marge Totale', 'Nb Commandes', 'Panier Moyen'],
            'Valeur': [
                df['CA Ligne'].sum(),
                df['Marge Ligne'].sum(),
                df['N° Commande'].nunique(),
                df['CA Ligne'].sum() / df['N° Commande'].nunique() if df['N° Commande'].nunique() > 0 else 0
            ]
        })
        resume.to_excel(writer, sheet_name='Résumé', index=False)

    output.seek(0)
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="jumia_analytics_export.xlsx"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_export_csv(request):
    """Export des données en CSV"""
    import csv
    from io import StringIO

    data = LigneCommande.objects.select_related(
        'commande__client', 'produit'
    ).values(
        'commande__numero_commande',
        'commande__date_commande',
        'commande__client__nom_client',
        'commande__client__region',
        'produit__code_article',
        'produit__nom_article',
        'quantite',
        'ca_ligne'
    )

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Commande', 'Date', 'Client', 'Région', 'Code', 'Article', 'Qté', 'CA'])

    for d in data:
        writer.writerow([
            d['commande__numero_commande'],
            d['commande__date_commande'],
            d['commande__client__nom_client'],
            d['commande__client__region'],
            d['produit__code_article'],
            d['produit__nom_article'],
            d['quantite'],
            d['ca_ligne']
        ])

    response = HttpResponse(output.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="jumia_analytics.csv"'
    return response


# ─────────────────────────────────────────────
# IMPORT DE DONNÉES
# ─────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_import_excel(request):
    """Import des données depuis Excel (ETAT.xlsx)"""
    import pandas as pd
    from io import BytesIO

    if 'file' not in request.FILES:
        return Response({'error': 'Aucun fichier fourni'}, status=400)

    file_obj = request.FILES['file']

    try:
        buf = BytesIO(file_obj.read())

        # Lecture des différentes feuilles
        df_ventes = pd.read_excel(buf, sheet_name=0)

        # Mapping des colonnes (adapté selon structure ETAT.xlsx)
        # Exemple de mapping - à adapter selon ton fichier réel

        result = {
            'lignes_importees': len(df_ventes),
            'colonnes': list(df_ventes.columns),
            'message': 'Import réussi. Utilisez la commande management pour persister en base.'
        }

        return Response(result)

    except Exception as e:
        logger.error(f"Import error: {e}")
        return Response({'error': str(e)}, status=500)


# ─────────────────────────────────────────────
# FRONTEND — RENDU TEMPLATES
# ─────────────────────────────────────────────


# ═════════════════════════════════════════════
# FRONTEND — RENDU TEMPLATES
# ═════════════════════════════════════════════

def index(request):
    """Page accueil / Dashboard"""
    return render(request, "analytics/dashboard.html")


def login_page(request):
    """Page connexion"""
    return render(request, "analytics/login.html")


def configurator(request):
    """Page configuration KPIs"""
    return render(request, "analytics/configurator.html")


# ═════════════════════════════════════════════
# CONFIGURATION DES KPIs (Nouveau)
# ═════════════════════════════════════════════

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_indicateurs(request):
    """CRUD des indicateurs personnalises"""
    if request.method == 'GET':
        indicateurs = IndicateurPersonnalise.objects.filter(created_by=request.user)
        return Response([{
            'id': i.id_indicateur,
            'code': i.code,
            'nom': i.nom,
            'description': i.description,
            'type_calcul': i.type_calcul,
            'type_affichage': i.type_affichage,
            'champ_source': i.champ_source,
            'formule': i.formule,
            'seuil_alerte_min': float(i.seuil_alerte_min) if i.seuil_alerte_min else None,
            'seuil_alerte_max': float(i.seuil_alerte_max) if i.seuil_alerte_max else None,
            'icone': i.icone,
            'ordre': i.ordre_affichage,
            'visible': i.visible,
        } for i in indicateurs])

    elif request.method == 'POST':
        data = request.data
        indicateur = IndicateurPersonnalise.objects.create(
            code=data['code'],
            nom=data['nom'],
            description=data.get('description', ''),
            type_calcul=data.get('type_calcul', 'somme'),
            type_affichage=data.get('type_affichage', 'montant'),
            champ_source=data.get('champ_source', ''),
            formule=data.get('formule', ''),
            champ_numerateur=data.get('champ_numerateur', ''),
            champ_denominateur=data.get('champ_denominateur', ''),
            seuil_alerte_min=data.get('seuil_alerte_min'),
            seuil_alerte_max=data.get('seuil_alerte_max'),
            icone=data.get('icone', 'fa-chart-line'),
            ordre_affichage=data.get('ordre_affichage', 0),
            visible=data.get('visible', True),
            created_by=request.user
        )
        return Response({'id': indicateur.id_indicateur, 'message': 'Indicateur cree'}, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_indicateur_detail(request, pk):
    """Detail, modification, suppression d'un indicateur"""
    try:
        indicateur = IndicateurPersonnalise.objects.get(pk=pk, created_by=request.user)
    except IndicateurPersonnalise.DoesNotExist:
        return Response({'error': 'Indicateur non trouve'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': indicateur.id_indicateur,
            'code': indicateur.code,
            'nom': indicateur.nom,
            'description': indicateur.description,
            'type_calcul': indicateur.type_calcul,
            'type_affichage': indicateur.type_affichage,
            'champ_source': indicateur.champ_source,
            'formule': indicateur.formule,
            'champ_numerateur': indicateur.champ_numerateur,
            'champ_denominateur': indicateur.champ_denominateur,
            'seuil_alerte_min': float(indicateur.seuil_alerte_min) if indicateur.seuil_alerte_min else None,
            'seuil_alerte_max': float(indicateur.seuil_alerte_max) if indicateur.seuil_alerte_max else None,
            'couleur_positive': indicateur.couleur_positive,
            'couleur_negative': indicateur.couleur_negative,
            'icone': indicateur.icone,
            'ordre': indicateur.ordre_affichage,
            'visible': indicateur.visible,
        })

    elif request.method == 'PUT':
        data = request.data
        for field, value in data.items():
            if hasattr(indicateur, field):
                setattr(indicateur, field, value)
        indicateur.save()
        return Response({'message': 'Indicateur mis a jour'})

    elif request.method == 'DELETE':
        indicateur.delete()
        return Response({'message': 'Indicateur supprime'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_calculer_kpi(request, pk):
    """Calcule la valeur d'un KPI specifique"""
    from .kpi_engine import get_kpi_engine

    filtres = {
        'region': request.data.get('region'),
        'periode': request.data.get('periode'),
        'date_debut': request.data.get('date_debut'),
        'date_fin': request.data.get('date_fin'),
    }
    filtres = {k: v for k, v in filtres.items() if v is not None}

    engine = get_kpi_engine()
    resultat = engine.calculer_kpi(pk, filtres)

    return Response(resultat)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_kpi_par_dimension(request, pk):
    """Calcule un KPI groupe par dimension"""
    from .kpi_engine import get_kpi_engine

    dimension_code = request.data.get('dimension')
    filtres = request.data.get('filtres', {})

    engine = get_kpi_engine()
    resultat = engine.calculer_par_dimension(pk, dimension_code, filtres)

    return Response(resultat)


# ═════════════════════════════════════════════
# CONFIGURATION DU PROJET & CANEVAS
# ═════════════════════════════════════════════

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_configurations(request):
    """CRUD des configurations de projet"""
    if request.method == 'GET':
        configs = ConfigurationProjet.objects.filter(created_by=request.user)
        return Response([{
            'id': c.id_config,
            'nom': c.nom_projet,
            'description': c.description,
            'theme': c.theme_couleur,
            'colonnes_canevas': c.colonnes_canevas,
            'created_at': c.created_at.isoformat()
        } for c in configs])

    elif request.method == 'POST':
        data = request.data
        config = ConfigurationProjet.objects.create(
            nom_projet=data.get('nom', 'Mon Dashboard'),
            description=data.get('description', ''),
            colonnes_canevas=data.get('colonnes_canevas', []),
            theme_couleur=data.get('theme', '#f97316'),
            created_by=request.user
        )
        return Response({'id': config.id_config, 'message': 'Configuration creee'}, status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_configuration_detail(request, pk):
    """Detail, modification, suppression d'une configuration"""
    try:
        config = ConfigurationProjet.objects.get(pk=pk, created_by=request.user)
    except ConfigurationProjet.DoesNotExist:
        return Response({'error': 'Configuration non trouvee'}, status=404)

    if request.method == 'GET':
        return Response({
            'id': config.id_config,
            'nom': config.nom_projet,
            'description': config.description,
            'theme': config.theme_couleur,
            'colonnes_canevas': config.colonnes_canevas,
            'logo': config.logo_url,
        })

    elif request.method == 'PUT':
        data = request.data
        config.nom_projet = data.get('nom', config.nom_projet)
        config.description = data.get('description', config.description)
        config.colonnes_canevas = data.get('colonnes_canevas', config.colonnes_canevas)
        config.theme_couleur = data.get('theme', config.theme_couleur)
        config.save()
        return Response({'message': 'Configuration mise a jour'})

    elif request.method == 'DELETE':
        config.delete()
        return Response({'message': 'Configuration supprimee'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_generer_canevas(request, pk):
    """Genere le canevas Excel pour une configuration"""
    from .kpi_engine import get_kpi_engine
    from django.http import HttpResponse

    engine = get_kpi_engine(pk)
    output = engine.generer_canevas_excel(pk)

    if output is None:
        return Response({'error': 'Configuration non trouvee'}, status=404)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="canevas_{pk}.xlsx"'
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_importer_canevas(request, pk):
    """Importe les donnees depuis le canevas rempli"""
    from .kpi_engine import get_kpi_engine

    if 'file' not in request.FILES:
        return Response({'error': 'Aucun fichier fourni'}, status=400)

    engine = get_kpi_engine(pk)
    resultat = engine.importer_canevas(pk, request.FILES['file'])

    return Response(resultat)


# ═════════════════════════════════════════════
# WIDGETS DASHBOARD
# ═════════════════════════════════════════════

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_widgets(request):
    """CRUD des widgets dashboard"""
    if request.method == 'GET':
        widgets = WidgetDashboard.objects.filter(created_by=request.user)
        return Response([{
            'id': w.id_widget,
            'nom': w.nom,
            'type': w.type_widget,
            'indicateur': w.indicateur.nom if w.indicateur else None,
            'position': {'x': w.position_x, 'y': w.position_y},
            'taille': {'w': w.largeur, 'h': w.hauteur},
        } for w in widgets])

    elif request.method == 'POST':
        data = request.data
        widget = WidgetDashboard.objects.create(
            nom=data['nom'],
            type_widget=data['type_widget'],
            indicateur_id=data['indicateur_id'],
            position_x=data.get('position_x', 0),
            position_y=data.get('position_y', 0),
            largeur=data.get('largeur', 6),
            hauteur=data.get('hauteur', 4),
            created_by=request.user
        )
        if data.get('dimensions'):
            widget.dimensions.set(data['dimensions'])
        return Response({'id': widget.id_widget, 'message': 'Widget cree'}, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dashboard_dynamique(request):
    """
    Genere le dashboard complet avec les widgets et KPIs configures.
    Retourne les donnees pour chaque widget.
    """
    from .kpi_engine import get_kpi_engine

    widgets = WidgetDashboard.objects.filter(created_by=request.user, indicateur__visible=True)

    dashboard_data = []
    engine = get_kpi_engine()

    for widget in widgets:
        try:
            kpi_data = engine.calculer_kpi(widget.indicateur_id, {})
            dashboard_data.append({
                'widget': {
                    'id': widget.id_widget,
                    'nom': widget.nom,
                    'type': widget.type_widget,
                    'position': {'x': widget.position_x, 'y': widget.position_y},
                    'taille': {'w': widget.largeur, 'h': widget.hauteur},
                },
                'data': kpi_data
            })
        except Exception as e:
            logger.error(f"Erreur widget {widget.id_widget}: {e}")
            continue

    return Response({'widgets': dashboard_data})
