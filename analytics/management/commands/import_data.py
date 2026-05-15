"""
Commande Django pour importer ETAT.xlsx vers PostgreSQL.
Génère aussi les données comportementales (sessions, événements).
Aligné avec le mémoire PFE §2.2.2 et §4.2.
"""
import os
import random
from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd
from django.core.management.base import BaseCommand
from django.db import transaction

from analytics.models import (
    Client, Produit, Categorie, Commercial, Commande, LigneCommande,
    SessionNavigation, EvenementComportemental
)


class Command(BaseCommand):
    help = 'Importe les données ETAT.xlsx et génère les données comportementales'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='data/ETAT.xlsx',
            help='Chemin vers le fichier Excel'
        )
        parser.add_argument(
            '--generate-behavior',
            action='store_true',
            default=True,
            help='Générer les données comportementales'
        )
        parser.add_argument(
            '--n-sessions',
            type=int,
            default=5000,
            help='Nombre de sessions de navigation à générer'
        )

    def handle(self, *args, **options):
        file_path = options['file']
        generate_behavior = options['generate_behavior']
        n_sessions = options['n_sessions']

        if not os.path.exists(file_path):
            self.stdout.write(
                self.style.ERROR(f"Fichier non trouvé: {file_path}")
            )
            return

        self.stdout.write(self.style.NOTICE("Début de l'import..."))

        # Lecture du fichier
        try:
            df = pd.read_excel(file_path, sheet_name=0)
            self.stdout.write(f"Lecture réussie: {len(df)} lignes, {list(df.columns)} colonnes")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erreur lecture: {e}"))
            return

        # Mapping des colonnes (à adapter selon ton ETAT.xlsx)
        # Colonnes attendues: Date, Code Clt, Client, Commercial, Region, 
        # Code Art, Article, Categorie, Qte, PU, Remise, CA, Marge

        with transaction.atomic():
            self._import_dimensions(df)
            self._import_commandes(df)

            if generate_behavior:
                self._generate_behavioral_data(n_sessions)

            self._recalculate_rfm()

        self.stdout.write(self.style.SUCCESS("Import terminé avec succès !"))
        self._print_stats()

    def _import_dimensions(self, df):
        """Importe les dimensions (catégories, produits, clients, commerciaux)"""
        self.stdout.write("Import des dimensions...")

        # Catégories
        categories = df['Categorie'].dropna().unique() if 'Categorie' in df.columns else ['Général']
        for cat_name in categories:
            Categorie.objects.get_or_create(
                nom_categorie=str(cat_name),
                defaults={'description': f'Catégorie {cat_name}'}
            )

        # Commerciaux
        if 'Commercial' in df.columns:
            commerciaux = df['Commercial'].dropna().unique()
            for i, comm_name in enumerate(commerciaux):
                Commercial.objects.get_or_create(
                    code_commercial=f"COM{i+1:03d}",
                    defaults={'nom_commercial': str(comm_name)}
                )

        # Clients
        if 'Code Clt' in df.columns and 'Client' in df.columns:
            clients_df = df[['Code Clt', 'Client', 'Region']].drop_duplicates()
            for _, row in clients_df.iterrows():
                Client.objects.get_or_create(
                    code_client=str(row['Code Clt']),
                    defaults={
                        'nom_client': str(row['Client']),
                        'region': str(row['Region']) if pd.notna(row['Region']) else None,
                        'ville': str(row['Region']) if pd.notna(row['Region']) else None
                    }
                )

        # Produits
        if 'Code Art' in df.columns and 'Article' in df.columns:
            produits_df = df[['Code Art', 'Article', 'Categorie', 'PU']].drop_duplicates()
            for _, row in produits_df.iterrows():
                cat_name = str(row['Categorie']) if pd.notna(row['Categorie']) else 'Général'
                categorie, _ = Categorie.objects.get_or_create(nom_categorie=cat_name)

                prix = Decimal(str(row['PU'])) if pd.notna(row['PU']) else Decimal('0')

                Produit.objects.get_or_create(
                    code_article=str(row['Code Art']),
                    defaults={
                        'nom_article': str(row['Article']),
                        'categorie': categorie,
                        'prix_unitaire': prix,
                        'cout_unitaire': prix * Decimal('0.6'),  # Marge 40%
                        'stock_disponible': random.randint(10, 1000)
                    }
                )

        self.stdout.write(self.style.SUCCESS("Dimensions importées"))

    def _import_commandes(self, df):
        """Importe les commandes et lignes de commande"""
        self.stdout.write("Import des commandes...")

        # Groupement par commande (supposons que chaque ligne = une commande unique pour simplifier)
        # Si tu as un N° Commande, adapte ici

        for idx, row in df.iterrows():
            try:
                # Client
                code_client = str(row['Code Clt']) if 'Code Clt' in df.columns and pd.notna(row['Code Clt']) else f"CLT{idx+1:04d}"
                client, _ = Client.objects.get_or_create(
                    code_client=code_client,
                    defaults={'nom_client': str(row['Client']) if 'Client' in df.columns and pd.notna(row['Client']) else f"Client {idx+1}"}
                )

                # Commercial
                comm_name = str(row['Commercial']) if 'Commercial' in df.columns and pd.notna(row['Commercial']) else "Général"
                commercial, _ = Commercial.objects.get_or_create(
                    code_commercial=f"COM{idx%10+1:03d}",
                    defaults={'nom_commercial': comm_name}
                )

                # Date
                if 'Date' in df.columns and pd.notna(row['Date']):
                    if isinstance(row['Date'], datetime):
                        date_cmd = row['Date'].date()
                    else:
                        try:
                            date_cmd = pd.to_datetime(row['Date']).date()
                        except:
                            date_cmd = datetime(2024, 1, 1).date()
                else:
                    date_cmd = datetime(2024, random.randint(1, 12), random.randint(1, 28)).date()

                # Commande
                commande, created = Commande.objects.get_or_create(
                    numero_commande=f"CMD{idx+1:06d}",
                    defaults={
                        'client': client,
                        'commercial': commercial,
                        'date_commande': date_cmd,
                        'mois': date_cmd.month,
                        'annee': date_cmd.year,
                        'trimestre': (date_cmd.month - 1) // 3 + 1,
                    }
                )

                # Produit
                code_art = str(row['Code Art']) if 'Code Art' in df.columns and pd.notna(row['Code Art']) else f"ART{idx%50+1:04d}"
                produit, _ = Produit.objects.get_or_create(
                    code_article=code_art,
                    defaults={
                        'nom_article': str(row['Article']) if 'Article' in df.columns and pd.notna(row['Article']) else f"Article {idx+1}",
                        'categorie': Categorie.objects.first(),
                        'prix_unitaire': Decimal('100'),
                        'cout_unitaire': Decimal('60')
                    }
                )

                # Ligne de commande
                qte = int(row['Qte']) if 'Qte' in df.columns and pd.notna(row['Qte']) else random.randint(1, 10)
                pu = Decimal(str(row['PU'])) if 'PU' in df.columns and pd.notna(row['PU']) else produit.prix_unitaire
                remise = Decimal(str(row['Remise'])) if 'Remise' in df.columns and pd.notna(row['Remise']) else Decimal('0')

                LigneCommande.objects.create(
                    commande=commande,
                    produit=produit,
                    quantite=qte,
                    prix_unitaire=pu,
                    remise_ligne=remise
                )

                if (idx + 1) % 1000 == 0:
                    self.stdout.write(f"  {idx + 1} lignes traitées...")

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Erreur ligne {idx}: {e}"))
                continue

        self.stdout.write(self.style.SUCCESS(f"Commandes importées: {Commande.objects.count()}"))

    def _generate_behavioral_data(self, n_sessions):
        """Génère des données comportementales réalistes (§4.2)"""
        self.stdout.write(f"Génération de {n_sessions} sessions de navigation...")

        clients = list(Client.objects.all())
        produits = list(Produit.objects.all())

        if not clients or not produits:
            self.stdout.write(self.style.WARNING("Pas assez de clients/produits pour générer des données comportementales"))
            return

        sources = ['organic', 'paid', 'social', 'direct', 'email']
        pages = [
            '/produits', '/panier', '/checkout', '/produit-detail',
            '/categories', '/promotions', '/nouveautes', '/compte'
        ]

        sessions_crees = 0
        evenements_crees = 0

        for i in range(n_sessions):
            client = random.choice(clients) if random.random() > 0.3 else None

            session = SessionNavigation.objects.create(
                client=client,
                ip_adresse=f"192.168.{random.randint(0,255)}.{random.randint(0,255)}",
                user_agent="Mozilla/5.0 (compatible; AnalyticsBot/1.0)",
                source_trafic=random.choice(sources),
                duree_secondes=random.randint(30, 1800)
            )
            sessions_crees += 1

            # Nombre d'événements par session
            n_events = random.randint(1, 15)

            for j in range(n_events):
                produit = random.choice(produits)
                timestamp = datetime.now() - timedelta(
                    days=random.randint(0, 90),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59)
                )

                # Distribution réaliste des événements
                r = random.random()
                if r < 0.6:
                    event_type = 'vue_produit'
                elif r < 0.75:
                    event_type = 'ajout_panier'
                elif r < 0.85:
                    event_type = 'abandon_panier'
                elif r < 0.95:
                    event_type = 'recherche'
                else:
                    event_type = 'favori'

                EvenementComportemental.objects.create(
                    session=session,
                    client=client,
                    produit=produit,
                    type_evenement=event_type,
                    timestamp=timestamp,
                    url_page=random.choice(pages),
                    duree_engagement=random.randint(5, 300)
                )
                evenements_crees += 1

            if (i + 1) % 500 == 0:
                self.stdout.write(f"  {i + 1} sessions générées...")

        self.stdout.write(self.style.SUCCESS(
            f"Données comportementales: {sessions_crees} sessions, {evenements_crees} événements"
        ))

    def _recalculate_rfm(self):
        """Recalcule les scores RFM après import"""
        self.stdout.write("Recalcul RFM...")

        from django.db.models import Max

        date_ref = Commande.objects.aggregate(max_date=Max('date_commande'))['max_date']
        if not date_ref:
            return

        for client in Client.objects.all():
            commandes = Commande.objects.filter(client=client)
            if not commandes.exists():
                continue

            derniere_cmd = commandes.order_by('-date_commande').first()
            recence = (date_ref - derniere_cmd.date_commande).days
            frequence = commandes.count()
            montant = LigneCommande.objects.filter(
                commande__client=client
            ).aggregate(total=Sum('ca_ligne'))['total'] or 0

            r_score = max(1, 5 - recence // 30)
            f_score = min(5, frequence)
            m_score = min(5, int(montant / 10000) + 1)
            score_rfm = r_score * 100 + f_score * 10 + m_score

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

        self.stdout.write(self.style.SUCCESS("RFM recalculé"))

    def _print_stats(self):
        """Affiche les statistiques finales"""
        self.stdout.write("
" + "="*50)
        self.stdout.write(self.style.NOTICE("STATISTIQUES"))
        self.stdout.write("="*50)
        self.stdout.write(f"Catégories: {Categorie.objects.count()}")
        self.stdout.write(f"Produits: {Produit.objects.count()}")
        self.stdout.write(f"Clients: {Client.objects.count()}")
        self.stdout.write(f"Commerciaux: {Commercial.objects.count()}")
        self.stdout.write(f"Commandes: {Commande.objects.count()}")
        self.stdout.write(f"Lignes commande: {LigneCommande.objects.count()}")
        self.stdout.write(f"Sessions navigation: {SessionNavigation.objects.count()}")
        self.stdout.write(f"Événements comportementaux: {EvenementComportemental.objects.count()}")
        self.stdout.write("="*50)
