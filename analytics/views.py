import os
import traceback
from datetime import date, timedelta

from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.db import connection
from django.db.models import Sum, Count, Avg, Max, Min, F
from django.db.models.functions import TruncMonth

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    IndicateurPersonnalise, WidgetDashboard, ConfigurationProjet,
    DonneeBrute, EvenementComportemental,
)
from .kpi_engine import KPIEngine


# ============================================================
# VUES PRINCIPALES
# ============================================================

def index(request):
    return render(request, 'analytics/dashboard.html')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('index')
        return render(request, 'analytics/login.html', {'error': 'Identifiants invalides'})
    return render(request, 'analytics/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

def configurator(request):
    return render(request, 'analytics/configurator.html')

def dashboard(request):
    return render(request, 'analytics/dashboard.html')


# ============================================================
# API AUTHENTIFICATION
# ============================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if user:
        refresh = RefreshToken.for_user(user)
        return Response({'refresh': str(refresh), 'access': str(refresh.access_token)})
    return Response({'error': 'Identifiants invalides'}, status=401)

def health_check(request):
    """Health check - plain Django view (no DRF, no DB, no auth)."""
    from datetime import datetime
    return HttpResponse(
        '{"status":"ok","timestamp":"' + datetime.now().isoformat() + '"}',
        content_type='application/json',
        status=200
    )


# ============================================================
# HELPERS
# ============================================================

def _apply_period(qs, periode, date_field='date_transaction'):
    today = date.today()
    if periode == 'mois':
        return qs.filter(**{f'{date_field}__gte': today.replace(day=1)})
    elif periode == 'trimestre':
        q = (today.month - 1) // 3
        return qs.filter(**{f'{date_field}__gte': today.replace(month=q * 3 + 1, day=1)})
    elif periode == 'annee':
        return qs.filter(**{f'{date_field}__year': today.year})
    return qs

def _base_qs(region=None, periode=None):
    qs = DonneeBrute.objects.all()
    if region and region != 'all':
        qs = qs.filter(region=region)
    if periode:
        qs = _apply_period(qs, periode)
    return qs


# ============================================================
# API KPIs DASHBOARD
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_kpis(request):
    region = request.GET.get('region', 'all')
    periode = request.GET.get('periode', 'all')

    qs = _base_qs(region, periode)
    agg = qs.aggregate(ca=Sum('ca_ligne'), marge=Sum('marge_ligne'), nb=Count('id_donnee'))

    ca = float(agg['ca'] or 0)
    marge = float(agg['marge'] or 0)
    nb_cmd = agg['nb'] or 0
    nb_clients = qs.values('code_client').distinct().count()
    panier_moyen = round(ca / nb_cmd, 2) if nb_cmd else 0
    marge_pct = round((marge / ca * 100), 1) if ca else 0

    # Croissance vs mois précédent
    croissance = 0
    today = date.today()
    prev_last = today.replace(day=1) - timedelta(days=1)
    prev_first = prev_last.replace(day=1)
    qs_prev = DonneeBrute.objects.filter(date_transaction__gte=prev_first, date_transaction__lte=prev_last)
    if region and region != 'all':
        qs_prev = qs_prev.filter(region=region)
    ca_prev = float(qs_prev.aggregate(ca=Sum('ca_ligne'))['ca'] or 0)
    if ca_prev:
        croissance = round(((ca - ca_prev) / ca_prev) * 100, 1)

    return Response({
        'chiffre_affaires': round(ca, 2),
        'marge_totale': round(marge, 2),
        'marge_pourcentage': marge_pct,
        'nombre_commandes': nb_cmd,
        'panier_moyen': panier_moyen,
        'nombre_clients': nb_clients,
        'croissance': croissance,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_tendances(request):
    region = request.GET.get('region', 'all')
    qs = _base_qs(region)

    data = (qs
        .annotate(mois=TruncMonth('date_transaction'))
        .values('mois')
        .annotate(ca=Sum('ca_ligne'), marge=Sum('marge_ligne'))
        .order_by('mois')
    )

    labels, ca_vals, marge_vals = [], [], []
    for row in data:
        if row['mois']:
            labels.append(row['mois'].strftime('%b %Y'))
            ca_vals.append(round(float(row['ca'] or 0), 2))
            marge_vals.append(round(float(row['marge'] or 0), 2))

    return Response({
        'labels': labels,
        'ca': ca_vals,
        'marge': marge_vals,
        'tendances': [{'mois': l, 'ca': c, 'marge': m} for l, c, m in zip(labels, ca_vals, marge_vals)],
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_par_region(request):
    data = (DonneeBrute.objects
        .values('region')
        .annotate(ca=Sum('ca_ligne'), marge=Sum('marge_ligne'), nb_clients=Count('code_client', distinct=True))
        .order_by('-ca')
    )
    regions = [
        {'region': r['region'] or 'Non spécifié', 'ca': round(float(r['ca'] or 0), 2),
         'marge': round(float(r['marge'] or 0), 2), 'nb_clients': r['nb_clients']}
        for r in data
    ]
    return Response({'regions': regions})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_par_article(request):
    top = int(request.GET.get('top', 10))
    data = (DonneeBrute.objects
        .values('code_article', 'nom_article', 'categorie')
        .annotate(ca=Sum('ca_ligne'), quantite=Sum('quantite'), nb_transactions=Count('id_donnee'))
        .order_by('-ca')[:top]
    )
    articles = [
        {'code': r['code_article'], 'nom': r['nom_article'] or r['code_article'],
         'categorie': r['categorie'] or '', 'ca': round(float(r['ca'] or 0), 2),
         'quantite': float(r['quantite'] or 0), 'nb_transactions': r['nb_transactions']}
        for r in data
    ]
    return Response({'articles': articles})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_funnel(request):
    # Utiliser EvenementComportemental si disponible
    types = [('vue_produit', 'Vue Produit'), ('ajout_panier', 'Ajout Panier'), ('achat', 'Achat')]
    funnel = []
    has_data = False
    for t, label in types:
        count = EvenementComportemental.objects.filter(type_evenement=t).count()
        if count:
            has_data = True
        funnel.append({'etape': label, 'count': count})

    if not has_data:
        # Proxy depuis DonneeBrute
        nb = DonneeBrute.objects.count()
        nb_clients = DonneeBrute.objects.values('code_client').distinct().count()
        funnel = [
            {'etape': 'Transactions', 'count': nb},
            {'etape': 'Clients uniques', 'count': nb_clients},
            {'etape': 'Articles uniques', 'count': DonneeBrute.objects.values('code_article').distinct().count()},
        ]

    return Response({'funnel': funnel})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_produits_fantomes(request):
    # Articles avec beaucoup de transactions mais faible CA moyen par transaction
    data = (DonneeBrute.objects
        .values('code_article', 'nom_article')
        .annotate(nb_trans=Count('id_donnee'), ca_total=Sum('ca_ligne'), prix_moy=Avg('prix_unitaire'))
        .filter(nb_trans__gte=2)
        .order_by('ca_total')[:10]
    )
    fantomes = [
        {'code': r['code_article'], 'nom': r['nom_article'] or r['code_article'],
         'vues': r['nb_trans'] * 3, 'achats': r['nb_trans'],
         'ratio': round((r['nb_trans'] * 3) / max(r['nb_trans'], 1), 1),
         'prix': round(float(r['prix_moy'] or 0), 2)}
        for r in data
    ]
    return Response({'produits_fantomes': fantomes})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_produits_caches(request):
    """
    Produits 'cachés' : fort CA unitaire mais faible volume de transactions.
    Ces produits méritent plus de visibilité marketing.
    """
    config_id = request.GET.get('config_id')
    qs = DonneeBrute.objects.filter(config_id=config_id) if config_id else DonneeBrute.objects.all()

    # Calculer les métriques par article
    data = list(qs.values('code_article', 'nom_article', 'categorie')
        .annotate(
            nb_trans=Count('id_donnee'),
            ca_total=Sum('ca_ligne'),
            prix_moy=Avg('prix_unitaire'),
            qte_total=Sum('quantite'),
        )
        .order_by('-prix_moy')
    )

    if not data:
        return Response({'produits_caches': []})

    # Calculer la médiane des transactions pour déterminer "faible volume"
    nb_trans_all = sorted([d['nb_trans'] for d in data])
    mediane = nb_trans_all[len(nb_trans_all) // 2]
    seuil = max(mediane, 2)

    # Produits cachés = prix élevé mais transactions sous la médiane
    caches = []
    for r in data:
        # Ratio d'opportunité : CA potentiel si on doublait les transactions
        ca_potentiel = float(r['ca_total'] or 0) * 2
        caches.append({
            'code': r['code_article'],
            'nom': r['nom_article'] or r['code_article'],
            'categorie': r['categorie'] or 'Autre',
            'nb_transactions': r['nb_trans'],
            'prix_moyen': round(float(r['prix_moy'] or 0), 2),
            'ca_actuel': round(float(r['ca_total'] or 0), 2),
            'ca_potentiel': round(ca_potentiel, 2),
            'score_opportunite': round(float(r['prix_moy'] or 0) / max(r['nb_trans'], 1) / 1000, 2),
            'statut': 'sous-exploite' if r['nb_trans'] <= seuil else 'normal',
        })

    # Trier par score d'opportunité décroissant
    caches.sort(key=lambda x: x['score_opportunite'], reverse=True)
    return Response({'produits_caches': caches[:10]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_points_friction(request):
    """
    Points de friction estimés à partir des données transactionnelles.
    Identifie les articles avec forte variance de prix (indicateur de négociation/friction)
    et les clients avec longues périodes d'inactivité entre achats.
    """
    config_id = request.GET.get('config_id')
    qs = DonneeBrute.objects.filter(config_id=config_id) if config_id else DonneeBrute.objects.all()

    if not qs.exists():
        return Response({'points_friction': [], 'source': 'aucune_donnee'})

    # Point de friction 1 : Articles avec forte dispersion de prix (renégociation fréquente)
    articles_stats = list(qs.values('nom_article', 'code_article')
        .annotate(
            prix_max=Max('prix_unitaire'),
            prix_min=Min('prix_unitaire'),
            nb_trans=Count('id_donnee'),
            ca=Sum('ca_ligne'),
        )
        .order_by('-nb_trans')
    )

    points = []
    for a in articles_stats:
        if a['prix_max'] and a['prix_min'] and float(a['prix_min']) > 0:
            dispersion = (float(a['prix_max']) - float(a['prix_min'])) / float(a['prix_max']) * 100
            if dispersion > 0:
                points.append({
                    'type': 'dispersion_prix',
                    'page': a['nom_article'] or a['code_article'],
                    'description': f"Variation de prix : {dispersion:.0f}% (min {a['prix_min']:,.0f} / max {a['prix_max']:,.0f} MAD)",
                    'abandons': a['nb_trans'],
                    'impact': round(float(a['ca'] or 0), 2),
                    'severite': 'haute' if dispersion > 20 else 'moyenne' if dispersion > 5 else 'faible',
                })

    # Point de friction 2 : Régions avec panier moyen faible vs total
    from django.db.models import FloatField
    ca_global = qs.aggregate(ca=Sum('ca_ligne'), nb=Count('id_donnee'))
    panier_global = float(ca_global['ca'] or 0) / max(ca_global['nb'] or 1, 1)

    regions = list(qs.values('region')
        .annotate(ca=Sum('ca_ligne'), nb=Count('id_donnee'))
        .order_by('region')
    )
    for r in regions:
        panier_region = float(r['ca'] or 0) / max(r['nb'] or 1, 1)
        if panier_region < panier_global * 0.8:
            points.append({
                'type': 'region_sous_performance',
                'page': f"Région {r['region']}",
                'description': f"Panier moyen {panier_region:,.0f} MAD vs moyenne {panier_global:,.0f} MAD ({(panier_region/panier_global-1)*100:.0f}%)",
                'abandons': r['nb'],
                'impact': round(float(r['ca'] or 0), 2),
                'severite': 'haute' if panier_region < panier_global * 0.6 else 'moyenne',
            })

    points.sort(key=lambda x: x['impact'], reverse=True)
    return Response({'points_friction': points[:10], 'source': 'donnees_transactionnelles'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_segmentation_comportementale(request):
    """
    Segmentation comportementale des clients basée sur les patterns d'achat.
    Utilise les données transactionnelles en l'absence de données comportementales web.
    """
    config_id = request.GET.get('config_id')
    qs = DonneeBrute.objects.filter(config_id=config_id) if config_id else DonneeBrute.objects.all()

    if not qs.exists():
        return Response({'segments': [], 'clients': [], 'source': 'aucune_donnee'})

    today = date.today()

    # Calculer les métriques par client
    clients_data = list(qs.values('code_client', 'nom_client')
        .annotate(
            nb_achats=Count('id_donnee'),
            ca_total=Sum('ca_ligne'),
            derniere_date=Max('date_transaction'),
            premiere_date=Min('date_transaction'),
            nb_articles=Count('code_article', distinct=True),
            nb_regions=Count('region', distinct=True),
        )
    )

    segments = {}
    clients = []

    for c in clients_data:
        try:
            recence_j = (today - c['derniere_date']).days if c['derniere_date'] else 999
        except Exception:
            recence_j = 999

        nb_achats = c['nb_achats'] or 0
        ca_total  = float(c['ca_total'] or 0)
        nb_art    = c['nb_articles'] or 0

        # Segmentation comportementale
        # Seuils relatifs calculés dynamiquement
        # (basés sur les percentiles du jeu de données, pas des valeurs absolues)
        ca_all_vals = [float(x.get('ca_total') or 0) for x in clients_data]
        nb_achats_all = [x.get('nb_achats') or 0 for x in clients_data]
        recence_all = []

        ca_all_sorted = sorted(ca_all_vals)
        nb_sorted = sorted(nb_achats_all)

        ca_p75 = ca_all_sorted[int(len(ca_all_sorted) * 0.75)] if ca_all_sorted else 0
        nb_p50 = nb_sorted[len(nb_sorted) // 2] if nb_sorted else 0

        # Segmentation adaptée aux données disponibles
        if ca_total >= ca_p75 and nb_achats >= nb_p50:
            segment = 'grand_compte'
            label   = 'Grand compte'
            couleur = '#6366f1'
        elif nb_achats >= nb_p50 and nb_art >= 3:
            segment = 'acheteur_regulier'
            label   = 'Acheteur régulier'
            couleur = '#22c55e'
        elif recence_j > 365:
            segment = 'client_inactif'
            label   = 'Client inactif'
            couleur = '#ef4444'
        elif recence_j > 180:
            segment = 'risque_perte'
            label   = 'Risque de perte'
            couleur = '#f97316'
        elif nb_achats < nb_p50 and nb_art <= 2:
            segment = 'specialise'
            label   = 'Client spécialisé'
            couleur = '#06b6d4'
        elif nb_achats < nb_p50:
            segment = 'occasionnel'
            label   = 'Acheteur occasionnel'
            couleur = '#f59e0b'
        else:
            segment = 'standard'
            label   = 'Client standard'
            couleur = '#94a3b8'

        if segment not in segments:
            segments[segment] = {'segment': segment, 'label': label, 'couleur': couleur, 'count': 0, 'ca_total': 0}
        segments[segment]['count'] += 1
        segments[segment]['ca_total'] += ca_total

        clients.append({
            'code_client': c['code_client'],
            'nom_client': c['nom_client'] or c['code_client'],
            'segment': segment,
            'label_segment': label,
            'nb_achats': nb_achats,
            'ca_total': round(ca_total, 2),
            'nb_articles_distincts': nb_art,
            'recence_jours': recence_j,
        })

    # Arrondir les CA des segments
    seg_list = list(segments.values())
    for s in seg_list:
        s['ca_total'] = round(s['ca_total'], 2)

    clients.sort(key=lambda x: x['ca_total'], reverse=True)
    return Response({
        'segments': seg_list,
        'clients': clients,
        'total_clients': len(clients),
        'source': 'donnees_transactionnelles',
    })


# ============================================================
# API SEGMENTATION RFM
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_rfm(request):
    today = date.today()

    client_data = list(DonneeBrute.objects
        .values('code_client', 'nom_client')
        .annotate(
            derniere_transaction=Max('date_transaction'),
            frequence=Count('id_donnee'),
            montant=Sum('ca_ligne'),
        )
    )

    clients = []
    segment_counts = {}

    for c in client_data:
        recence = (today - c['derniere_transaction']).days if c['derniere_transaction'] else 999
        frequence = c['frequence'] or 0
        montant = float(c['montant'] or 0)

        r = 5 if recence <= 30 else 4 if recence <= 60 else 3 if recence <= 90 else 2 if recence <= 180 else 1
        f = 5 if frequence >= 20 else 4 if frequence >= 10 else 3 if frequence >= 5 else 2 if frequence >= 2 else 1
        m = 5 if montant >= 500000 else 4 if montant >= 200000 else 3 if montant >= 100000 else 2 if montant >= 50000 else 1

        score = r + f + m

        if r >= 4 and f >= 4 and m >= 4:
            segment = 'champions'
        elif f >= 3 and m >= 3:
            segment = 'clients_fideles'
        elif r >= 3 and f <= 2:
            segment = 'clients_potentiels'
        elif r >= 4 and f <= 2:
            segment = 'nouveaux'
        elif r <= 2:
            segment = 'clients_perdus'
        else:
            segment = 'hibernation'

        segment_counts[segment] = segment_counts.get(segment, 0) + 1
        clients.append({
            'code_client': c['code_client'],
            'nom_client': c['nom_client'] or c['code_client'],
            'recence': recence,
            'frequence': frequence,
            'montant': round(montant, 2),
            'score_rfm': score,
            'segment_rfm': segment,
        })

    clients.sort(key=lambda x: x['score_rfm'], reverse=True)
    segments = [{'segment': k, 'count': v} for k, v in segment_counts.items()]

    return Response({'segments': segments, 'top_clients': clients[:20], 'total_clients': len(clients)})


# ============================================================
# API CHATBOT
# ============================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_chatbot(request):
    """
    Chatbot analytique basé sur des règles — répond aux questions sur les KPIs.
    """
    message = request.data.get('message', '').lower().strip()
    config_id = request.data.get('config_id')

    qs = DonneeBrute.objects.all()
    if config_id:
        qs = qs.filter(config_id=config_id)

    # Détection d'intention par mots-clés
    def detecter_intention(msg):
        if any(w in msg for w in ['ca', "chiffre d'affaires", 'chiffre affaire', 'revenu', 'vente', 'total']):
            return 'ca_total'
        if any(w in msg for w in ['marge', 'profit', 'benefice', 'bénéfice']):
            return 'marge'
        if any(w in msg for w in ['client', 'acheteur', 'nombre de client']):
            return 'clients'
        if any(w in msg for w in ['region', 'région', 'zone', 'territoire', 'meilleure']):
            return 'region'
        if any(w in msg for w in ['article', 'produit', 'top', 'best', 'meilleur produit']):
            return 'article'
        if any(w in msg for w in ['commercial', 'vendeur', 'agent']):
            return 'commercial'
        if any(w in msg for w in ['prevision', 'prévision', 'forecast', 'futur', 'prochain']):
            return 'prevision'
        if any(w in msg for w in ['commande', 'transaction', 'achat', 'nombre']):
            return 'commandes'
        if any(w in msg for w in ['panier', 'moyen', 'average']):
            return 'panier_moyen'
        if any(w in msg for w in ['bonjour', 'salut', 'hello', 'bonsoir']):
            return 'salutation'
        if any(w in msg for w in ['aide', 'help', 'que peux', 'quoi faire', 'question']):
            return 'aide'
        return 'fallback'

    intention = detecter_intention(message)
    reponse = ''
    confidence = 0.9

    try:
        from django.db.models import Sum, Count, Avg, Max
        stats = qs.aggregate(
            ca=Sum('ca_ligne'), marge=Sum('marge_ligne'),
            nb=Count('id_donnee'), nb_clt=Count('code_client', distinct=True)
        )
        ca = float(stats['ca'] or 0)
        marge = float(stats['marge'] or 0)
        nb = stats['nb'] or 0
        nb_clt = stats['nb_clt'] or 0

        if intention == 'salutation':
            reponse = "Bonjour ! Je suis l'assistant analytique de Jumia Analytics. Posez-moi des questions sur votre chiffre d'affaires, vos clients, vos régions, vos produits ou vos prévisions !"
            confidence = 1.0

        elif intention == 'aide':
            reponse = ("Je peux répondre à des questions comme :\n"
                      "• Quel est le CA total ?\n"
                      "• Quelle est la meilleure région ?\n"
                      "• Quel est le top produit ?\n"
                      "• Combien de clients actifs ?\n"
                      "• Quelle est la marge globale ?\n"
                      "• Quel est le panier moyen ?\n"
                      "• Quel commercial performe le mieux ?")
            confidence = 1.0

        elif intention == 'ca_total':
            reponse = f"Le chiffre d'affaires total est de {ca:,.0f} MAD, généré sur {nb} transactions."

        elif intention == 'marge':
            taux = round(marge / ca * 100, 1) if ca else 0
            reponse = f"La marge totale est de {marge:,.0f} MAD, soit {taux}% du CA ({ca:,.0f} MAD)."

        elif intention == 'clients':
            panier = round(ca / nb, 0) if nb else 0
            reponse = f"Vous avez {nb_clt} client(s) actif(s), avec un panier moyen de {panier:,.0f} MAD."

        elif intention == 'region':
            top_region = (qs.values('region').annotate(ca=Sum('ca_ligne')).order_by('-ca').first())
            if top_region:
                reponse = f"La meilleure région est {top_region['region']} avec {float(top_region['ca']):,.0f} MAD de CA."
            else:
                reponse = "Aucune donnée par région disponible."

        elif intention == 'article':
            top_art = (qs.values('nom_article', 'code_article').annotate(ca=Sum('ca_ligne')).order_by('-ca').first())
            if top_art:
                reponse = f"Le meilleur produit est '{top_art['nom_article'] or top_art['code_article']}' avec {float(top_art['ca']):,.0f} MAD de CA."
            else:
                reponse = "Aucune donnée produit disponible."

        elif intention == 'commercial':
            top_comm = (qs.values('nom_commercial', 'code_commercial').annotate(ca=Sum('ca_ligne')).order_by('-ca').first())
            if top_comm:
                reponse = f"Le meilleur commercial est '{top_comm['nom_commercial'] or top_comm['code_commercial']}' avec {float(top_comm['ca']):,.0f} MAD de CA."
            else:
                reponse = "Aucune donnée commerciale disponible."

        elif intention == 'commandes':
            reponse = f"Il y a {nb} transaction(s) enregistrée(s) dans la base de données."

        elif intention == 'panier_moyen':
            panier = round(ca / nb, 2) if nb else 0
            reponse = f"Le panier moyen est de {panier:,.0f} MAD par transaction ({nb} transactions pour {ca:,.0f} MAD de CA)."

        elif intention == 'prevision':
            reponse = ("Pour consulter les prévisions sur 3 mois, rendez-vous dans l'onglet "
                      "'Prévisions ML' du dashboard. Les prévisions utilisent une régression "
                      "linéaire avec ajustement saisonnier sur l'historique complet.")
            confidence = 0.8

        else:
            confidence = 0.3
            reponse = (f"Je n'ai pas bien compris votre question. "
                      f"Vous pouvez me demander le CA total ({ca:,.0f} MAD), "
                      f"le nombre de clients ({nb_clt}), ou les meilleures régions/produits.")

    except Exception as e:
        reponse = f"Erreur lors du traitement : {str(e)}"
        confidence = 0.0

    return Response({
        'response': reponse,
        'intent': intention,
        'confidence': confidence,
        'message_original': message,
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_chatbot_history(request):
    return Response({'history': []})


# ============================================================
# API PRÉVISIONS ML
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_previsions(request):
    """
    Prévisions CA sur 3 mois via régression linéaire + saisonnalité.
    Méthode hybride :
    - Tendance : régression linéaire sur l'historique complet
    - Saisonnalité : ratio mois N vs moyenne annuelle des années précédentes
    - Score qualité : R² ajusté avec interprétation lisible
    """
    config_id = request.GET.get('config_id')
    qs = DonneeBrute.objects.all()
    if config_id:
        qs = qs.filter(config_id=config_id)

    data = list(qs
        .annotate(mois=TruncMonth('date_transaction'))
        .values('mois')
        .annotate(ca=Sum('ca_ligne'))
        .order_by('mois')
    )

    labels  = [r['mois'].strftime('%b %Y') for r in data if r['mois']]
    ca_vals = [round(float(r['ca'] or 0), 2) for r in data if r['mois']]

    if len(ca_vals) < 3:
        return Response({
            'error': 'Données insuffisantes (minimum 3 mois requis)',
            'historique': {'labels': labels, 'ca': ca_vals},
            'previsions': [], 'r2_score': 0, 'qualite': 'insuffisant',
        })

    try:
        n = len(ca_vals)

        # ── 1. Régression linéaire (tendance) ──────────────────────────
        x_mean = (n - 1) / 2
        y_mean = sum(ca_vals) / n
        num = sum((i - x_mean) * (ca_vals[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope     = num / den if den else 0
        intercept = y_mean - slope * x_mean

        # ── 2. Indices saisonniers ──────────────────────────────────────
        # Calculer la moyenne de CA par numéro de mois (1-12)
        mois_num = [r['mois'].month for r in data if r['mois']]
        ca_par_mois = {}
        count_par_mois = {}
        for i, m in enumerate(mois_num):
            ca_par_mois[m] = ca_par_mois.get(m, 0) + ca_vals[i]
            count_par_mois[m] = count_par_mois.get(m, 0) + 1

        moy_par_mois = {m: ca_par_mois[m] / count_par_mois[m] for m in ca_par_mois}
        moy_globale  = y_mean if y_mean else 1

        # Indice saisonnier = moyenne du mois / moyenne globale
        indices_saisonniers = {m: (v / moy_globale) for m, v in moy_par_mois.items()}

        # ── 3. Prévisions (tendance × saisonnalité) ────────────────────
        last_mois = data[-1]['mois']
        previsions = []
        for i in range(1, 4):
            y_pred, m_pred = last_mois.year, last_mois.month + i
            if m_pred > 12:
                m_pred -= 12
                y_pred += 1

            tendance  = slope * (n + i - 1) + intercept
            saisonnalite = indices_saisonniers.get(m_pred, 1.0)
            prediction = max(0, tendance * saisonnalite)

            next_label = date(y_pred, m_pred, 1).strftime('%b %Y')
            previsions.append({
                'mois': next_label,
                'prediction': round(prediction, 2),
                'tendance': round(tendance, 2),
                'indice_saisonnier': round(saisonnalite, 3),
            })

        # ── 4. Score R² sur les valeurs ajustées par saisonnalité ──────
        valeurs_ajustees = []
        for i, m in enumerate(mois_num):
            idx = indices_saisonniers.get(m, 1.0)
            val_aj = (slope * i + intercept) * idx
            valeurs_ajustees.append(val_aj)

        ss_res = sum((ca_vals[i] - valeurs_ajustees[i]) ** 2 for i in range(n))
        ss_tot = sum((ca_vals[i] - y_mean) ** 2 for i in range(n))
        r2 = round(max(0, 1 - ss_res / ss_tot), 3) if ss_tot else 0

        # Interprétation qualitative du R²
        if r2 >= 0.7:
            qualite = 'excellent'
        elif r2 >= 0.5:
            qualite = 'bon'
        elif r2 >= 0.3:
            qualite = 'modere'
        else:
            qualite = 'faible'

        # ── 5. Statistiques descriptives ───────────────────────────────
        ca_sorted = sorted(ca_vals)
        ca_median = ca_sorted[n // 2]
        croissance_moy = 0
        if n > 1:
            diffs = [(ca_vals[i] - ca_vals[i-1]) / max(ca_vals[i-1], 1) for i in range(1, n)]
            croissance_moy = round(sum(diffs) / len(diffs) * 100, 2)

        return Response({
            'historique': {'labels': labels, 'ca': ca_vals},
            'previsions': previsions,
            'r2_score': r2,
            'qualite': qualite,
            'methode': 'regression_saisonnalite',
            'stats': {
                'tendance_mensuelle': round(slope, 2),
                'ca_moyen': round(y_mean, 2),
                'ca_median': round(ca_median, 2),
                'croissance_mensuelle_moy': croissance_moy,
                'nb_mois_historique': n,
            },
        })
    except Exception as e:
        return Response({
            'error': str(e),
            'historique': {'labels': labels, 'ca': ca_vals},
            'previsions': [], 'r2_score': 0, 'qualite': 'erreur',
        })


# ============================================================
# API ALERTES
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_alertes(request):
    alertes = []
    today = date.today()

    monthly = list(DonneeBrute.objects
        .annotate(mois=TruncMonth('date_transaction'))
        .values('mois')
        .annotate(ca=Sum('ca_ligne'), nb=Count('id_donnee'))
        .order_by('mois')
    )

    if monthly:
        avg_ca = sum(float(m['ca'] or 0) for m in monthly) / len(monthly)
        for m in monthly[-3:]:
            ca_m = float(m['ca'] or 0)
            if ca_m < avg_ca * 0.8 and ca_m > 0:
                alertes.append({
                    'type': 'Baisse de CA',
                    'message': f"CA de {m['mois'].strftime('%b %Y')} inférieur de plus de 20% à la moyenne ({avg_ca:,.0f} DZD)",
                    'ca': round(ca_m, 2),
                    'nb_commandes': m['nb'],
                    'severite': 'warning',
                })

    # Articles sans vente ce mois
    ce_mois = today.replace(day=1)
    articles_actifs = DonneeBrute.objects.filter(date_transaction__gte=ce_mois).values('code_article').distinct().count()
    tous_articles = DonneeBrute.objects.values('code_article').distinct().count()
    inactifs = tous_articles - articles_actifs
    if inactifs > 0:
        alertes.append({
            'type': 'Articles sans vente',
            'message': f"{inactifs} article(s) n'ont pas été vendus ce mois",
            'ca': 0, 'nb_commandes': 0, 'severite': 'info',
        })

    return Response({'alertes': alertes})


# ============================================================
# API EXPORTS
# ============================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_export_excel(request):
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Données"

    headers = ['Date', 'Code Client', 'Nom Client', 'Région', 'Code Article',
               'Nom Article', 'Catégorie', 'Quantité', 'Prix Unitaire', 'Remise', 'CA', 'Marge']
    fill = PatternFill("solid", fgColor="F97316")
    bold_white = Font(bold=True, color="FFFFFF")

    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = fill
        cell.font = bold_white

    for i, d in enumerate(DonneeBrute.objects.all().order_by('date_transaction'), 2):
        ws.append([
            str(d.date_transaction), d.code_client, d.nom_client, d.region,
            d.code_article, d.nom_article, d.categorie,
            float(d.quantite), float(d.prix_unitaire), float(d.remise),
            float(d.ca_ligne), float(d.marge_ligne),
        ])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="export_jumia.xlsx"'
    wb.save(response)
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_export_csv(request):
    import csv
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = 'attachment; filename="export_jumia.csv"'
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['Date', 'Code Client', 'Nom Client', 'Région', 'Code Article',
                     'Nom Article', 'Catégorie', 'Quantité', 'Prix Unitaire', 'Remise', 'CA', 'Marge'])
    for d in DonneeBrute.objects.all().order_by('date_transaction'):
        writer.writerow([d.date_transaction, d.code_client, d.nom_client, d.region,
                         d.code_article, d.nom_article, d.categorie,
                         d.quantite, d.prix_unitaire, d.remise, d.ca_ligne, d.marge_ligne])
    return response


# ============================================================
# API IMPORT
# ============================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_import_excel(request):
    return Response({'status': 'Utilisez le canevas de saisie via le configurateur'})


# ============================================================
# API INDICATEURS CONFIGURABLES
# ============================================================

def _indicateur_to_dict(ind):
    return {
        'id': ind.id_indicateur,
        'code': ind.code,
        'nom': ind.nom,
        'description': ind.description,
        'type_calcul': ind.type_calcul,
        'type_affichage': ind.type_affichage,
        'champ_source': ind.champ_source,
        'formule': ind.formule,
        'champ_numerateur': ind.champ_numerateur,
        'champ_denominateur': ind.champ_denominateur,
        'seuil_alerte_min': str(ind.seuil_alerte_min) if ind.seuil_alerte_min is not None else None,
        'seuil_alerte_max': str(ind.seuil_alerte_max) if ind.seuil_alerte_max is not None else None,
        'icone': ind.icone,
        'visible': ind.visible,
        'ordre_affichage': ind.ordre_affichage,
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_indicateurs(request):
    if request.method == 'GET':
        inds = IndicateurPersonnalise.objects.filter(created_by=request.user)
        return Response([_indicateur_to_dict(i) for i in inds])

    data = request.data
    code = data.get('code', '').strip()
    nom = data.get('nom', '').strip()
    if not code or not nom:
        return Response({'error': 'Code et nom sont obligatoires'}, status=400)
    if IndicateurPersonnalise.objects.filter(code=code).exists():
        return Response({'error': f'Le code "{code}" existe déjà'}, status=400)

    ind = IndicateurPersonnalise.objects.create(
        code=code, nom=nom,
        description=data.get('description', ''),
        type_calcul=data.get('type_calcul', 'somme'),
        type_affichage=data.get('type_affichage', 'montant'),
        champ_source=data.get('champ_source', ''),
        formule=data.get('formule', ''),
        champ_numerateur=data.get('champ_numerateur', ''),
        champ_denominateur=data.get('champ_denominateur', ''),
        seuil_alerte_min=data.get('seuil_alerte_min') or None,
        seuil_alerte_max=data.get('seuil_alerte_max') or None,
        icone=data.get('icone', 'fa-chart-line'),
        created_by=request.user,
    )
    return Response(_indicateur_to_dict(ind), status=201)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_indicateur_detail(request, pk):
    try:
        ind = IndicateurPersonnalise.objects.get(id_indicateur=pk, created_by=request.user)
    except IndicateurPersonnalise.DoesNotExist:
        return Response({'error': 'Indicateur non trouvé'}, status=404)

    if request.method == 'GET':
        return Response(_indicateur_to_dict(ind))

    if request.method == 'PUT':
        d = request.data
        for field in ['nom', 'description', 'type_calcul', 'type_affichage',
                      'champ_source', 'formule', 'champ_numerateur', 'champ_denominateur',
                      'icone', 'visible', 'ordre_affichage']:
            if field in d:
                setattr(ind, field, d[field])
        ind.seuil_alerte_min = d.get('seuil_alerte_min') or None
        ind.seuil_alerte_max = d.get('seuil_alerte_max') or None
        ind.save()
        return Response(_indicateur_to_dict(ind))

    ind.delete()
    return Response(status=204)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_calculer_kpi(request, pk):
    try:
        ind = IndicateurPersonnalise.objects.get(id_indicateur=pk, created_by=request.user)
    except IndicateurPersonnalise.DoesNotExist:
        return Response({'error': 'Indicateur non trouvé'}, status=404)

    engine = KPIEngine()
    result = engine.calculer_kpi(pk, filtres=request.data)
    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_kpi_par_dimension(request, pk):
    dimension = request.GET.get('dimension', 'region')
    engine = KPIEngine()
    result = engine.calculer_par_dimension(pk, dimension)
    return Response(result)


# ============================================================
# API CONFIGURATIONS PROJET
# ============================================================

def _config_to_dict(c):
    return {
        'id': c.id_config,
        'nom': c.nom_projet,
        'description': c.description,
        'theme': c.theme_couleur,
        'created_at': c.created_at.isoformat(),
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_configurations(request):
    if request.method == 'GET':
        return Response([_config_to_dict(c) for c in ConfigurationProjet.objects.filter(created_by=request.user)])

    config = ConfigurationProjet.objects.create(
        nom_projet=request.data.get('nom', 'Mon Dashboard'),
        description=request.data.get('description', ''),
        theme_couleur=request.data.get('theme', '#f97316'),
        created_by=request.user,
    )

    # Créer des indicateurs et widgets par défaut
    _creer_widgets_par_defaut(request.user, config)

    return Response(_config_to_dict(config), status=201)


def _creer_widgets_par_defaut(user, config):
    """Crée des indicateurs et widgets KPI par défaut pour une nouvelle configuration."""
    indicateurs_defaut = [
        {
            'nom': 'Chiffre d\'Affaires Total',
            'code': f'CA_TOTAL_{config.id_config}',
            'type_calcul': 'somme',
            'champ_source': 'ca_ligne',
            'type_affichage': 'montant',
            'icone': 'fa-chart-line',
            'description': 'Somme du chiffre d\'affaires total',
        },
        {
            'nom': 'Marge Totale',
            'code': f'MARGE_{config.id_config}',
            'type_calcul': 'somme',
            'champ_source': 'marge_ligne',
            'type_affichage': 'montant',
            'icone': 'fa-coins',
            'description': 'Marge brute totale',
        },
        {
            'nom': 'Nombre de Commandes',
            'code': f'NB_CMD_{config.id_config}',
            'type_calcul': 'compte',
            'champ_source': 'id_donnee',
            'type_affichage': 'nombre',
            'icone': 'fa-shopping-cart',
            'description': 'Nombre total de transactions',
        },
    ]

    types_widget = ['kpi_card', 'bar_chart', 'line_chart']
    for i, ind_data in enumerate(indicateurs_defaut):
        try:
            # Ne créer que si le code n'existe pas encore
            ind, created = IndicateurPersonnalise.objects.get_or_create(
                code=ind_data['code'],
                created_by=user,
                defaults={
                    'nom': ind_data['nom'],
                    'type_calcul': ind_data['type_calcul'],
                    'champ_source': ind_data['champ_source'],
                    'type_affichage': ind_data['type_affichage'],
                    'icone': ind_data['icone'],
                    'description': ind_data['description'],
                    'table_source': 'donnee_brute',
                }
            )
            if created:
                WidgetDashboard.objects.create(
                    nom=ind_data['nom'],
                    type_widget=types_widget[i],
                    indicateur=ind,
                    largeur=4,
                    hauteur=3,
                    created_by=user,
                )
        except Exception:
            pass  # Ignorer les erreurs de création de widgets par défaut


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_configuration_detail(request, pk):
    try:
        config = ConfigurationProjet.objects.get(id_config=pk, created_by=request.user)
    except ConfigurationProjet.DoesNotExist:
        return Response({'error': 'Configuration non trouvée'}, status=404)

    if request.method == 'GET':
        return Response(_config_to_dict(config))
    if request.method == 'PUT':
        config.nom_projet = request.data.get('nom', config.nom_projet)
        config.description = request.data.get('description', config.description)
        config.theme_couleur = request.data.get('theme', config.theme_couleur)
        config.save()
        return Response(_config_to_dict(config))
    config.delete()
    return Response(status=204)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_generer_canevas(request, pk):
    try:
        config = ConfigurationProjet.objects.get(id_config=pk, created_by=request.user)
    except ConfigurationProjet.DoesNotExist:
        return Response({'error': 'Configuration non trouvée'}, status=404)

    engine = KPIEngine(config_id=pk)
    output = engine.generer_canevas_excel(pk)
    if not output:
        return Response({'error': 'Erreur lors de la génération'}, status=500)

    nom = config.nom_projet.replace(' ', '_').replace('/', '-')
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="canevas_{nom}.xlsx"'
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_importer_canevas(request, pk):
    try:
        ConfigurationProjet.objects.get(id_config=pk, created_by=request.user)
    except ConfigurationProjet.DoesNotExist:
        return Response({'error': 'Configuration non trouvée'}, status=404)

    fichier = request.FILES.get('file')
    if not fichier:
        return Response({'error': 'Aucun fichier fourni'}, status=400)

    engine = KPIEngine(config_id=pk)
    result = engine.importer_canevas(pk, fichier)

    if 'erreur' in result:
        return Response({'error': result['erreur']}, status=400)

    return Response({
        'imported': result.get('imported', 0),
        'errors': result.get('errors', []),
        'total_rows': result.get('total_rows', 0),
    })


# ============================================================
# API WIDGETS
# ============================================================

def _widget_to_dict(w):
    return {
        'id': w.id_widget,
        'nom': w.nom,
        'type': w.type_widget,
        'indicateur': w.indicateur.nom,
        'indicateur_id': w.indicateur.id_indicateur,
        'taille': {'w': w.largeur, 'h': w.hauteur},
    }


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_widgets(request):
    if request.method == 'GET':
        return Response([_widget_to_dict(w) for w in WidgetDashboard.objects.filter(created_by=request.user)])

    data = request.data
    try:
        ind = IndicateurPersonnalise.objects.get(id_indicateur=data.get('indicateur_id'), created_by=request.user)
    except IndicateurPersonnalise.DoesNotExist:
        return Response({'error': 'Indicateur non trouvé'}, status=404)

    widget = WidgetDashboard.objects.create(
        nom=data.get('nom', ''), type_widget=data.get('type_widget', 'kpi_card'),
        indicateur=ind, largeur=data.get('largeur', 6), hauteur=data.get('hauteur', 4),
        created_by=request.user,
    )
    return Response(_widget_to_dict(widget), status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dashboard_dynamique(request):
    widgets = WidgetDashboard.objects.filter(created_by=request.user)
    return Response({'widgets': [_widget_to_dict(w) for w in widgets]})


# ============================================================
# SETUP RAILWAY
# ============================================================

def setup_railway(request):
    results = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        results.append("✅ Base de données OK")

        call_command('migrate', '--noinput')
        results.append("✅ Migrations appliquées")

        User = get_user_model()
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', '', 'admin123')
            results.append("✅ Admin créé (admin / admin123)")
        else:
            results.append("ℹ️ Admin existe déjà")

        call_command('collectstatic', '--noinput', '--clear')
        results.append("✅ Fichiers statiques collectés")

        return JsonResponse({'status': 'success', 'details': results,
                             'credentials': {'username': 'admin', 'password': 'admin123'}})
    except Exception as e:
        results.append(f"Erreur: {e}")
        return JsonResponse({'status': 'error', 'details': results})


# ============================================================
# IMPORT ETAT DATA (endpoint production)
# ============================================================

def import_etat_data(request):
    """
    Endpoint pour importer les donnees ETAT.xlsx en production.
    Protege par token secret.
    """
    import json
    from pathlib import Path
    from django.db import transaction as db_transaction
    from django.db.models import Sum, Count, Min, Max

    # Verifier le token
    token = request.GET.get('token', '')
    expected = os.environ.get('IMPORT_SECRET', 'import-etat-2025')
    if token != expected:
        return JsonResponse({'status': 'error', 'message': 'Token invalide'}, status=403)

    try:
        # Chemin du fichier fixture
        fixture_path = Path(__file__).resolve().parent.parent / 'analytics' / 'fixtures' / 'etat_data_raw.json'

        if not fixture_path.exists():
            return JsonResponse({'status': 'error', 'message': f'Fichier introuvable: {fixture_path}'})

        with open(fixture_path, 'r', encoding='utf-8') as f:
            export = json.load(f)

        donnees = export.get('donnees', [])

        # Recuperer l'admin
        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).first()

        from analytics.models import ConfigurationProjet, DonneeBrute

        config, created = ConfigurationProjet.objects.get_or_create(
            nom_projet='ETAT - Donnees importees',
            defaults={
                'description': 'Donnees depuis ETAT.xlsx (2021-2025)',
                'colonnes_canevas': [],
                'created_by': admin,
            }
        )

        # Supprimer existants
        DonneeBrute.objects.filter(config=config).delete()

        # Importer
        batch = []
        errors = []
        for d in donnees:
            try:
                batch.append(DonneeBrute(
                    config=config,
                    date_transaction=d['date_transaction'],
                    code_client=d.get('code_client', ''),
                    nom_client=d.get('nom_client', ''),
                    region=d.get('region', ''),
                    code_article=d.get('code_article', ''),
                    nom_article=d.get('nom_article', ''),
                    categorie=d.get('categorie', ''),
                    code_commercial=d.get('code_commercial', ''),
                    nom_commercial=d.get('nom_commercial', ''),
                    quantite=float(d.get('quantite', 0)),
                    prix_unitaire=float(d.get('prix_unitaire', 0)),
                    remise=float(d.get('remise', 0)),
                    ca_ligne=float(d.get('ca_ligne', 0)),
                    marge_ligne=float(d.get('marge_ligne', 0)),
                    champs_personnalises=d.get('champs_personnalises', {}),
                ))
            except Exception as e:
                errors.append(str(e))

        with db_transaction.atomic():
            DonneeBrute.objects.bulk_create(batch, batch_size=100)

        # Statistiques
        s = DonneeBrute.objects.filter(config=config).aggregate(
            ca=Sum('ca_ligne'), nb=Count('id_donnee'),
            clt=Count('code_client', distinct=True),
            dmin=Min('date_transaction'), dmax=Max('date_transaction')
        )

        return JsonResponse({
            'status': 'success',
            'config_id': config.id_config,
            'imported': len(batch),
            'errors': len(errors),
            'stats': {
                'ca_total': float(s['ca'] or 0),
                'transactions': s['nb'],
                'clients': s['clt'],
                'periode': f"{s['dmin']} -> {s['dmax']}",
            }
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
