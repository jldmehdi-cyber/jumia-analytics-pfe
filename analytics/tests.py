"""
Tests unitaires pour l'application analytics.
Alignés avec le mémoire PFE §4.4 (Validation).
"""
from django.test import TestCase, Client as TestClient
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from analytics.models import (
    Client, Produit, Categorie, Commercial, Commande, LigneCommande,
    SessionNavigation, EvenementComportemental, ConversationChatbot,
    IntentChatbot, ParametreSysteme,
    # Configurables
    IndicateurPersonnalise, DimensionAnalyse, ConfigurationProjet,
    WidgetDashboard, DonneeBrute
)
from analytics.chatbot_engine import ChatbotEngine
from analytics.kpi_engine import KPIEngine


class ModelesTestCase(TestCase):
    """Tests des modèles de données"""

    def setUp(self):
        self.categorie = Categorie.objects.create(
            nom_categorie='Électronique',
            description='Produits électroniques'
        )
        self.produit = Produit.objects.create(
            code_article='ART001',
            nom_article='Smartphone',
            categorie=self.categorie,
            prix_unitaire=50000,
            cout_unitaire=30000,
            stock_disponible=100
        )
        self.client = Client.objects.create(
            code_client='CLT001',
            nom_client='Test Client',
            region='Alger',
            ville='Alger'
        )
        self.commercial = Commercial.objects.create(
            code_commercial='COM001',
            nom_commercial='Test Commercial',
            zone='Nord'
        )

    def test_produit_marge_auto(self):
        """Test calcul automatique de la marge"""
        self.assertEqual(self.produit.marge, 20000)

    def test_ligne_commande_calculs(self):
        """Test calculs CA et marge sur ligne de commande"""
        commande = Commande.objects.create(
            numero_commande='CMD001',
            client=self.client,
            commercial=self.commercial,
            date_commande='2024-01-15',
            mois=1, annee=2024, trimestre=1
        )
        ligne = LigneCommande.objects.create(
            commande=commande,
            produit=self.produit,
            quantite=2,
            prix_unitaire=50000,
            remise_ligne=10
        )
        self.assertEqual(float(ligne.ca_ligne), 90000.0)


class ModelesConfigurablesTestCase(TestCase):
    """Tests des modèles configurables"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.config = ConfigurationProjet.objects.create(
            nom_projet='Test Project',
            description='Projet de test',
            colonnes_canevas=[
                {'nom': 'Canal', 'type': 'texte', 'obligatoire': False},
                {'nom': 'CoutMarketing', 'type': 'montant', 'obligatoire': False}
            ],
            created_by=self.user
        )

    def test_indicateur_creation(self):
        """Test création d'un indicateur personnalisé"""
        ind = IndicateurPersonnalise.objects.create(
            code='ca_total',
            nom="Chiffre d'Affaires",
            type_calcul='somme',
            type_affichage='montant',
            champ_source='ca_ligne',
            created_by=self.user
        )
        self.assertEqual(ind.code, 'ca_total')
        self.assertTrue(ind.visible)

    def test_donnee_brute_import(self):
        """Test import de données brutes"""
        donnee = DonneeBrute.objects.create(
            config=self.config,
            date_transaction='2024-01-15',
            code_client='CLT001',
            nom_client='Test',
            code_article='ART001',
            nom_article='Produit',
            quantite=5,
            prix_unitaire=10000,
            remise=10,
            champs_personnalises={'Canal': 'Web', 'CoutMarketing': '5000'}
        )
        self.assertEqual(float(donnee.ca_ligne), 45000.0)  # 5 * 10000 * 0.9

    def test_widget_creation(self):
        """Test création d'un widget"""
        ind = IndicateurPersonnalise.objects.create(
            code='test_kpi', nom='Test KPI',
            type_calcul='somme', champ_source='ca_ligne',
            created_by=self.user
        )
        widget = WidgetDashboard.objects.create(
            nom='Test Widget',
            type_widget='kpi_card',
            indicateur=ind,
            position_x=0, position_y=0,
            largeur=6, hauteur=4,
            created_by=self.user
        )
        self.assertEqual(widget.type_widget, 'kpi_card')


class KPIEngineTestCase(TestCase):
    """Tests du moteur de calcul KPI"""

    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.config = ConfigurationProjet.objects.create(
            nom_projet='Test', created_by=self.user
        )
        # Créer des données de test
        for i in range(5):
            DonneeBrute.objects.create(
                config=self.config,
                date_transaction=f'2024-01-{10+i}',
                code_client=f'CLT00{i}',
                code_article=f'ART00{i}',
                quantite=2,
                prix_unitaire=10000,
                remise=0
            )
        self.indicateur = IndicateurPersonnalise.objects.create(
            code='ca_test', nom='CA Test',
            type_calcul='somme', type_affichage='montant',
            champ_source='ca_ligne', table_source='donnee_brute',
            created_by=self.user
        )

    def test_calculer_kpi_somme(self):
        """Test calcul somme d'un KPI"""
        engine = KPIEngine(self.config.id_config)
        result = engine.calculer_kpi(self.indicateur.id_indicateur)
        self.assertIn('valeur', result)
        self.assertEqual(result['valeur'], 100000.0)  # 5 * 2 * 10000

    def test_calculer_kpi_formule(self):
        """Test calcul avec formule personnalisée"""
        ind_formule = IndicateurPersonnalise.objects.create(
            code='panier_test', nom='Panier Test',
            type_calcul='formule', type_affichage='montant',
            formule='ca / 5',  # 5 commandes
            created_by=self.user
        )
        engine = KPIEngine(self.config.id_config)
        result = engine.calculer_kpi(ind_formule.id_indicateur)
        self.assertEqual(result['valeur'], 20000.0)  # 100000 / 5

    def test_generer_canevas(self):
        """Test génération du canevas Excel"""
        engine = KPIEngine(self.config.id_config)
        output = engine.generer_canevas_excel(self.config.id_config)
        self.assertIsNotNone(output)


class ChatbotTestCase(TestCase):
    """Tests du moteur de chatbot"""

    def setUp(self):
        self.chatbot = ChatbotEngine()
        self.chatbot.train()

    def test_predict_intent_kpi(self):
        """Test détection intention KPI"""
        result = self.chatbot.predict_intent("quel est le chiffre d'affaires")
        self.assertEqual(result['intent'], 'kpi_request')
        self.assertGreater(result['confidence'], 0.5)

    def test_predict_intent_greeting(self):
        """Test détection salutation"""
        result = self.chatbot.predict_intent("bonjour")
        self.assertEqual(result['intent'], 'greeting')

    def test_predict_intent_fallback(self):
        """Test fallback pour message inconnu"""
        result = self.chatbot.predict_intent("météo demain")
        self.assertEqual(result['intent'], 'fallback')

    def test_generate_response_structure(self):
        """Test structure de la réponse"""
        result = self.chatbot.generate_response("test", {
            'intent': 'kpi_request',
            'confidence': 0.9
        })
        self.assertIn('text', result)
        self.assertIn('sql_template', result)
        self.assertIn('viz_type', result)


class APITestCase(APITestCase):
    """Tests des endpoints API"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

        self.categorie = Categorie.objects.create(nom_categorie='Test')
        self.produit = Produit.objects.create(
            code_article='ART001', nom_article='Test',
            categorie=self.categorie, prix_unitaire=100, cout_unitaire=60
        )
        self.client_test = Client.objects.create(
            code_client='CLT001', nom_client='Test', region='Alger'
        )

    def test_health_check(self):
        """Test endpoint health"""
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'ok')

    def test_kpis_endpoint(self):
        """Test endpoint KPIs"""
        response = self.client.get('/api/kpis/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('chiffre_affaires', response.data)

    def test_chatbot_endpoint(self):
        """Test endpoint chatbot"""
        response = self.client.post('/api/chatbot/', {
            'message': 'bonjour',
            'session_id': 'test-session'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('intent', response.data)

    def test_indicateurs_crud(self):
        """Test CRUD indicateurs"""
        # Create
        response = self.client.post('/api/indicateurs/', {
            'code': 'test_api',
            'nom': 'Test API',
            'type_calcul': 'somme',
            'type_affichage': 'montant',
            'champ_source': 'ca_ligne'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        ind_id = response.data['id']

        # Read
        response = self.client.get(f'/api/indicateurs/{ind_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['code'], 'test_api')

        # Update
        response = self.client.put(f'/api/indicateurs/{ind_id}/', {
            'nom': 'Test API Modifié'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Delete
        response = self.client.delete(f'/api/indicateurs/{ind_id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_configurations_crud(self):
        """Test CRUD configurations projet"""
        response = self.client.post('/api/configurations/', {
            'nom': 'Projet Test',
            'description': 'Description test',
            'colonnes_canevas': [{'nom': 'TestCol', 'type': 'texte'}]
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


class ExportTestCase(APITestCase):
    """Tests des exports"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

    def test_export_excel(self):
        """Test export Excel"""
        response = self.client.get('/api/export/excel/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    def test_export_csv(self):
        """Test export CSV"""
        response = self.client.get('/api/export/csv/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Content-Type'], 'text/csv')


class CanevasTestCase(APITestCase):
    """Tests du canevas de saisie"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)
        self.config = ConfigurationProjet.objects.create(
            nom_projet='Test Canevas',
            created_by=self.user
        )

    def test_generer_canevas(self):
        """Test génération canevas"""
        response = self.client.get(f'/api/configurations/{self.config.id_config}/canevas/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
