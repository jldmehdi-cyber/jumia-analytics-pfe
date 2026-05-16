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

@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    from datetime import datetime
    return Response({'status': 'ok', 'timestamp': datetime.now().isoformat()})


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
    # Articles avec forte CA mais peu de transactions (produits premium sous-exploités)
    data = (DonneeBrute.objects
        .values('code_article', 'nom_article')
        .annotate(nb_trans=Count('id_donnee'), ca_total=Sum('ca_ligne'), prix_moy=Avg('prix_unitaire'))
        .filter(nb_trans__lte=5)
        .order_by('-ca_total')[:10]
    )
    caches = [
        {'code': r['code_article'], 'nom': r['nom_article'] or r['code_article'],
         'vues': r['nb_trans'], 'achats': r['nb_trans'],
         'ratio': round(1 / max(r['nb_trans'], 1), 2),
         'ca': round(float(r['ca_total'] or 0), 2)}
        for r in data
    ]
    return Response({'produits_caches': caches})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_points_friction(request):
    # Produits ajoutés au panier mais non achetés (EvenementComportemental)
    from django.db.models import OuterRef, Subquery
    abandons = (EvenementComportemental.objects
        .filter(type_evenement='abandon_panier')
        .values('produit__nom_article')
        .annotate(abandons=Count('id_evenement'))
        .order_by('-abandons')[:10]
    )
    points = [{'page': r['produit__nom_article'] or 'Inconnu', 'abandons': r['abandons']} for r in abandons]

    if not points:
        points = [{'page': 'Aucune donnée comportementale disponible', 'abandons': 0}]

    return Response({'points_friction': points})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_segmentation_comportementale(request):
    return Response({'segments': []})


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
    message = request.data.get('message', '')
    reponse = f"Vous avez demandé : « {message} ». Le chatbot NLP est en cours d'intégration."
    return Response({'response': reponse, 'intent': 'fallback', 'confidence': 0.0})

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
    data = list(DonneeBrute.objects
        .annotate(mois=TruncMonth('date_transaction'))
        .values('mois')
        .annotate(ca=Sum('ca_ligne'))
        .order_by('mois')
    )

    labels = [r['mois'].strftime('%b %Y') for r in data if r['mois']]
    ca_vals = [round(float(r['ca'] or 0), 2) for r in data if r['mois']]

    if len(ca_vals) < 3:
        return Response({
            'error': 'Données insuffisantes (minimum 3 mois requis)',
            'historique': {'labels': labels, 'ca': ca_vals},
            'previsions': [], 'r2_score': 0,
        })

    try:
        n = len(ca_vals)
        x_mean = (n - 1) / 2
        y_mean = sum(ca_vals) / n
        num = sum((i - x_mean) * (ca_vals[i] - y_mean) for i in range(n))
        den = sum((i - x_mean) ** 2 for i in range(n))
        slope = num / den if den else 0
        intercept = y_mean - slope * x_mean

        ss_res = sum((ca_vals[i] - (slope * i + intercept)) ** 2 for i in range(n))
        ss_tot = sum((ca_vals[i] - y_mean) ** 2 for i in range(n))
        r2 = round(1 - ss_res / ss_tot, 3) if ss_tot else 0

        last_mois = data[-1]['mois']
        previsions = []
        for i in range(1, 4):
            # Avancer d'un mois
            y, m = last_mois.year, last_mois.month + i
            if m > 12:
                m -= 12
                y += 1
            next_mois_label = date(y, m, 1).strftime('%b %Y')
            pred = round(max(0, slope * (n + i - 1) + intercept), 2)
            previsions.append({'mois': next_mois_label, 'prediction': pred})

        return Response({
            'historique': {'labels': labels, 'ca': ca_vals},
            'previsions': previsions,
            'r2_score': r2,
        })
    except Exception as e:
        return Response({'error': str(e), 'historique': {'labels': labels, 'ca': ca_vals}, 'previsions': [], 'r2_score': 0})


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
    return Response(_config_to_dict(config), status=201)


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
        results.append(f"❌ Erreur: {e}")
        return JsonResponse({'status': 'error', 'details': results})
