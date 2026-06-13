"""
Moteur de calcul dynamique des KPIs configurables.
Génère les requêtes SQL et calcule les valeurs selon la configuration utilisateur.
"""
import logging
from decimal import Decimal
from django.db import connection
from django.db.models import Sum, Avg, Count, Min, Max, F, Q
from django.db.models.functions import TruncMonth, TruncQuarter, TruncYear

from .models import IndicateurPersonnalise, DimensionAnalyse, DonneeBrute, ConfigurationProjet

logger = logging.getLogger('analytics')


class KPIEngine:
    """
    Moteur de calcul des KPIs personnalisés.
    Interprète la configuration et génère les résultats.
    """

    def __init__(self, config_id=None):
        self.config_id = config_id
        self.config = None
        if config_id:
            try:
                self.config = ConfigurationProjet.objects.get(id_config=config_id)
            except ConfigurationProjet.DoesNotExist:
                pass

    def calculer_kpi(self, indicateur_id, filtres=None):
        """
        Calcule la valeur d'un KPI selon sa configuration.

        Args:
            indicateur_id: ID de l'IndicateurPersonnalise
            filtres: dict avec 'region', 'periode', 'date_debut', 'date_fin'

        Returns:
            dict avec 'valeur', 'comparaison', 'alerte', 'details'
        """
        try:
            indicateur = IndicateurPersonnalise.objects.get(id_indicateur=indicateur_id)
        except IndicateurPersonnalise.DoesNotExist:
            return {'erreur': 'Indicateur non trouvé'}

        filtres = filtres or {}

        # Construire la requête de base
        qs = self._get_queryset_base(indicateur, filtres)

        # Appliquer le calcul
        resultat = self._appliquer_calcul(indicateur, qs)

        # Calcul période précédente pour comparaison
        comparaison = self._calculer_comparaison(indicateur, filtres)

        # Vérifier les alertes
        alerte = self._verifier_alertes(indicateur, resultat)

        return {
            'indicateur': {
                'code': indicateur.code,
                'nom': indicateur.nom,
                'description': indicateur.description,
                'type_affichage': indicateur.type_affichage,
                'icone': indicateur.icone,
            },
            'valeur': resultat,
            'comparaison': comparaison,
            'alerte': alerte,
            'filtres_appliques': filtres
        }

    def _get_queryset_base(self, indicateur, filtres):
        """Construit le queryset de base avec les filtres"""
        if self.config:
            qs = DonneeBrute.objects.filter(config=self.config)
        else:
            qs = DonneeBrute.objects.filter(config__created_by=indicateur.created_by)

        # Appliquer les filtres
        if filtres.get('region'):
            qs = qs.filter(region=filtres['region'])

        if filtres.get('date_debut'):
            qs = qs.filter(date_transaction__gte=filtres['date_debut'])
        if filtres.get('date_fin'):
            qs = qs.filter(date_transaction__lte=filtres['date_fin'])

        # Filtre période prédéfini
        periode = filtres.get('periode')
        if periode:
            from datetime import datetime, timedelta
            today = datetime.now().date()
            if periode == 'mois':
                qs = qs.filter(date_transaction__gte=today - timedelta(days=30))
            elif periode == 'trimestre':
                qs = qs.filter(date_transaction__gte=today - timedelta(days=90))
            elif periode == 'annee':
                qs = qs.filter(date_transaction__gte=today - timedelta(days=365))

        return qs

    def _appliquer_calcul(self, indicateur, qs):
        """Applique le type de calcul configuré"""
        type_calc = indicateur.type_calcul
        champ = indicateur.champ_source

        if type_calc == 'somme':
            result = qs.aggregate(r=Sum(champ))['r'] or 0

        elif type_calc == 'moyenne':
            result = qs.aggregate(r=Avg(champ))['r'] or 0

        elif type_calc == 'compte':
            result = qs.aggregate(r=Count(champ, distinct=True))['r'] or 0

        elif type_calc == 'min':
            result = qs.aggregate(r=Min(champ))['r'] or 0

        elif type_calc == 'max':
            result = qs.aggregate(r=Max(champ))['r'] or 0

        elif type_calc == 'ratio':
            num = indicateur.champ_numerateur
            den = indicateur.champ_denominateur
            agg = qs.aggregate(n=Sum(num), d=Sum(den))
            result = (agg['n'] or 0) / (agg['d'] or 1) if agg['d'] else 0

        elif type_calc == 'pourcentage':
            # Variation par rapport à période précédente
            result = 0  # Calculé séparément

        elif type_calc == 'formule':
            # Évaluation de formule personnalisée
            result = self._evaluer_formule(indicateur.formule, qs)

        else:
            result = 0

        return float(result) if result else 0

    def _evaluer_formule(self, formule, qs):
        """Évalue une formule personnalisée de manière sécurisée"""
        if not formule:
            return 0

        ca_total = qs.aggregate(r=Sum('ca_ligne'))['r'] or 0
        marge_total = qs.aggregate(r=Sum('marge_ligne'))['r'] or 0
        nb_cmd = qs.aggregate(r=Count('id_donnee', distinct=True))['r'] or 0
        qte_total = qs.aggregate(r=Sum('quantite'))['r'] or 0
        total_clients = qs.values('code_client').distinct().count()
        clients_recurrents = qs.values('code_client').annotate(nb=Count('id_donnee')).filter(nb__gt=1).count()
        clients_un_achat = total_clients - clients_recurrents
        taux_abandon_proxy = round(clients_un_achat / total_clients * 100, 2) if total_clients else 0

        context = {
            'ca': float(ca_total),
            'marge': float(marge_total),
            'nb_commandes': float(nb_cmd),
            'quantite': float(qte_total),
            'panier_moyen': float(ca_total) / float(nb_cmd) if nb_cmd else 0,
            'total_clients': float(total_clients),
            'clients_recurrents': float(clients_recurrents),
            'clients_un_achat': float(clients_un_achat),
            'taux_abandon': taux_abandon_proxy,
            'round': round, 'abs': abs, 'max': max, 'min': min,
        }

        try:
            result = eval(formule, {"__builtins__": {}}, context)
            return result
        except Exception as e:
            logger.error(f"Erreur formule KPI: {e}")
            return 0

    def _calculer_comparaison(self, indicateur, filtres):
        """Calcule la valeur pour la période précédente"""
        # Simplification : on retourne 0 pour l'instant
        # Implémentation complète nécessiterait de décaler les dates
        return {'valeur_precedente': 0, 'variation': 0}

    def _verifier_alertes(self, indicateur, valeur):
        """Vérifie si la valeur dépasse les seuils configurés"""
        alertes = []

        if indicateur.seuil_alerte_min is not None and valeur < float(indicateur.seuil_alerte_min):
            alertes.append({
                'type': 'seuil_min',
                'message': f"Valeur {valeur} inférieure au seuil minimum {indicateur.seuil_alerte_min}",
                'severite': 'critique' if valeur < float(indicateur.seuil_alerte_min) * 0.8 else 'warning'
            })

        if indicateur.seuil_alerte_max is not None and valeur > float(indicateur.seuil_alerte_max):
            alertes.append({
                'type': 'seuil_max',
                'message': f"Valeur {valeur} supérieure au seuil maximum {indicateur.seuil_alerte_max}",
                'severite': 'critique' if valeur > float(indicateur.seuil_alerte_max) * 1.2 else 'warning'
            })

        return alertes

    def calculer_par_dimension(self, indicateur_id, dimension_code, filtres=None):
        """
        Calcule un KPI groupé par une dimension (drill-down).
        Ex: CA par région, Ventes par commercial...
        """
        try:
            indicateur = IndicateurPersonnalise.objects.get(id_indicateur=indicateur_id)
            dimension = DimensionAnalyse.objects.get(code=dimension_code)
        except (IndicateurPersonnalise.DoesNotExist, DimensionAnalyse.DoesNotExist):
            return {'erreur': 'Indicateur ou dimension non trouvé'}

        filtres = filtres or {}
        qs = self._get_queryset_base(indicateur, filtres)

        # Mapping des dimensions vers les champs réels
        dim_mapping = {
            'region': 'region',
            'categorie': 'categorie',
            'commercial': 'code_commercial',
            'client': 'code_client',
            'mois': 'date_transaction__month',
            'annee': 'date_transaction__year',
        }

        champ_dim = dim_mapping.get(dimension.code, dimension.champ_sql)

        # Agrégation par dimension
        data = qs.values(champ_dim).annotate(
            valeur=Sum(indicateur.champ_source) if indicateur.type_calcul == 'somme' else Avg(indicateur.champ_source)
        ).order_by('-valeur')

        return {
            'dimension': dimension.nom,
            'indicateur': indicateur.nom,
            'data': [
                {
                    'libelle': d[champ_dim] or 'Non spécifié',
                    'valeur': float(d['valeur'] or 0)
                }
                for d in data
            ]
        }

    def generer_canevas_excel(self, config_id):
        """
        Génère un fichier Excel canevas pour la saisie des données.
        Les colonnes correspondent à la configuration du projet.
        """
        import pandas as pd
        from io import BytesIO

        try:
            config = ConfigurationProjet.objects.get(id_config=config_id)
        except ConfigurationProjet.DoesNotExist:
            return None

        # Colonnes de base
        colonnes = [
            'Date', 'Code Client', 'Nom Client', 'Région',
            'Code Article', 'Nom Article', 'Catégorie',
            'Code Commercial', 'Nom Commercial',
            'Quantité', 'Prix Unitaire', 'Remise (%)'
        ]

        # Ajouter les colonnes personnalisées
        if config.colonnes_canevas:
            for col in config.colonnes_canevas:
                if col.get('nom') not in colonnes:
                    colonnes.append(col['nom'])

        # Créer le DataFrame avec exemples
        df = pd.DataFrame(columns=colonnes)

        # Ajouter quelques lignes d'exemple
        exemples = [
            ['2024-01-15', 'CLT001', 'Client Exemple', 'Alger', 'ART001', 'Produit A', 'Électronique', 'COM001', 'Commercial 1', 5, 10000, 10],
            ['2024-01-16', 'CLT002', 'Client Test', 'Oran', 'ART002', 'Produit B', 'Maison', 'COM002', 'Commercial 2', 3, 15000, 5],
        ]

        for ex in exemples:
            row = dict(zip(colonnes, ex))
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)

        # Feuille d'instructions
        instructions = pd.DataFrame({
            'Champ': colonnes,
            'Type': ['Date', 'Texte', 'Texte', 'Texte', 'Texte', 'Texte', 'Texte', 'Texte', 'Texte', 'Nombre', 'Montant', 'Pourcentage'] + ['Texte'] * (len(colonnes) - 12),
            'Obligatoire': ['Oui', 'Oui', 'Non', 'Non', 'Oui', 'Non', 'Non', 'Non', 'Non', 'Oui', 'Oui', 'Non'] + ['Non'] * (len(colonnes) - 12),
            'Description': [
                'Date de la transaction (YYYY-MM-DD)',
                'Code unique du client',
                'Nom complet du client',
                'Région géographique',
                'Code unique de l\'article',
                'Designation de l\'article',
                'Catégorie du produit',
                'Code du commercial',
                'Nom du commercial',
                'Quantité vendue',
                'Prix unitaire en MAD',
                'Taux de remise en %'
            ] + ['Champ personnalisé'] * (len(colonnes) - 12)
        })

        # Export
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Données à saisir', index=False)
            instructions.to_excel(writer, sheet_name='Instructions', index=False)

            # Mise en forme
            worksheet = writer.sheets['Données à saisir']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

        output.seek(0)
        return output

    def importer_canevas(self, config_id, fichier_excel):
        """
        Importe les données depuis le canevas Excel rempli par l'utilisateur.
        """
        import pandas as pd

        try:
            config = ConfigurationProjet.objects.get(id_config=config_id)
        except ConfigurationProjet.DoesNotExist:
            return {'erreur': 'Configuration non trouvée'}

        try:
            df = pd.read_excel(fichier_excel, sheet_name='Données à saisir')
        except Exception as e:
            return {'erreur': f'Erreur lecture Excel: {e}'}

        imported = 0
        errors = []

        for idx, row in df.iterrows():
            try:
                # Mapping des colonnes
                donnee = DonneeBrute(
                    config=config,
                    date_transaction=pd.to_datetime(row.get('Date', row.get('date', row.get('DATE')))).date(),
                    code_client=str(row.get('Code Client', row.get('code_client', ''))),
                    nom_client=str(row.get('Nom Client', row.get('nom_client', ''))),
                    region=str(row.get('Région', row.get('region', row.get('REGION', '')))),
                    code_article=str(row.get('Code Article', row.get('code_article', ''))),
                    nom_article=str(row.get('Nom Article', row.get('nom_article', ''))),
                    categorie=str(row.get('Catégorie', row.get('categorie', row.get('CATEGORIE', '')))),
                    code_commercial=str(row.get('Code Commercial', row.get('code_commercial', ''))),
                    nom_commercial=str(row.get('Nom Commercial', row.get('nom_commercial', ''))),
                    quantite=float(row.get('Quantité', row.get('quantite', row.get('QUANTITE', 1)))),
                    prix_unitaire=float(row.get('Prix Unitaire', row.get('prix_unitaire', row.get('PU', 0)))),
                    remise=float(row.get('Remise (%)', row.get('remise', row.get('REMISE', 0)))),
                )

                # Champs personnalisés
                champs_perso = {}
                if config.colonnes_canevas:
                    for col in config.colonnes_canevas:
                        col_name = col['nom']
                        if col_name in row and col_name not in ['Date', 'Code Client', 'Code Article', 'Quantité', 'Prix Unitaire']:
                            champs_perso[col_name] = str(row[col_name])

                donnee.champs_personnalises = champs_perso
                donnee.save()
                imported += 1

            except Exception as e:
                errors.append(f"Ligne {idx + 2}: {str(e)}")

        return {
            'imported': imported,
            'errors': errors,
            'total_rows': len(df)
        }


# Singleton
def get_kpi_engine(config_id=None):
    return KPIEngine(config_id)
