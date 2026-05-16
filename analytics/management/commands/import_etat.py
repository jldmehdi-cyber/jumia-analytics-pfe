"""
Commande Django pour importer les données ETAT.xlsx en production.
Usage: python manage.py import_etat
"""
import json
import os
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Importe les donnees ETAT (2021-2025) depuis le fichier JSON fixture'

    def handle(self, *args, **options):
        from analytics.models import ConfigurationProjet, DonneeBrute

        User = get_user_model()
        admin = User.objects.filter(is_superuser=True).first()
        if not admin:
            self.stderr.write('Erreur: aucun superuser trouve. Creer un admin dabord.')
            return

        # Chemin du fichier JSON
        fixture_path = Path(__file__).resolve().parent.parent.parent.parent / 'analytics' / 'fixtures' / 'etat_data_raw.json'

        if not fixture_path.exists():
            self.stderr.write(f'Erreur: fichier {fixture_path} introuvable')
            return

        self.stdout.write(f'Lecture de {fixture_path}...')
        with open(fixture_path, 'r', encoding='utf-8') as f:
            export = json.load(f)

        donnees = export.get('donnees', [])
        self.stdout.write(f'{len(donnees)} transactions a importer')

        # Creer ou recuperer la configuration
        config, created = ConfigurationProjet.objects.get_or_create(
            nom_projet='ETAT - Donnees importees',
            defaults={
                'description': 'Donnees importees depuis ETAT.xlsx (2021-2025)',
                'colonnes_canevas': [],
                'created_by': admin,
            }
        )
        action = 'Creee' if created else 'Existante'
        self.stdout.write(f'Configuration: {action} (ID={config.id_config})')

        # Supprimer existants
        nb_del = DonneeBrute.objects.filter(config=config).count()
        if nb_del:
            DonneeBrute.objects.filter(config=config).delete()
            self.stdout.write(f'Supprime {nb_del} enregistrements existants')

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

        with transaction.atomic():
            DonneeBrute.objects.bulk_create(batch, batch_size=100)

        self.stdout.write(self.style.SUCCESS(
            f'Importation terminee: {len(batch)} lignes | Erreurs: {len(errors)}'
        ))

        # Statistiques
        from django.db.models import Sum, Count, Min, Max
        s = DonneeBrute.objects.filter(config=config).aggregate(
            ca=Sum('ca_ligne'), nb=Count('id_donnee'),
            clt=Count('code_client', distinct=True),
            dmin=Min('date_transaction'), dmax=Max('date_transaction')
        )
        self.stdout.write(f'CA Total       : {s["ca"]:,.0f} MAD')
        self.stdout.write(f'Transactions   : {s["nb"]}')
        self.stdout.write(f'Clients uniques: {s["clt"]}')
        self.stdout.write(f'Periode        : {s["dmin"]} -> {s["dmax"]}')
        self.stdout.write(self.style.SUCCESS(f'CONFIG ID = {config.id_config}'))
