"""
Moteur de chatbot analytique aligné avec le mémoire PFE §4.3.
Pipeline NLP : tokenisation → lemmatisation → stop words → TF-IDF → VotingClassifier.
"""
import os
import re
import pickle
import logging
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

# Tentative d'import NLTK
nltk_available = False
try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.stem import WordNetLemmatizer
    nltk_available = True
except ImportError:
    pass

logger = logging.getLogger('analytics')

# ─────────────────────────────────────────────
# STOP WORDS FRANÇAIS (fallback si NLTK non dispo)
# ─────────────────────────────────────────────
STOP_WORDS_FR = {
    'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'et', 'en', 'à', 'au',
    'aux', 'par', 'pour', 'avec', 'dans', 'sur', 'sous', 'ce', 'cet', 'cette',
    'ces', 'mon', 'ton', 'son', 'notre', 'votre', 'leur', 'ma', 'ta', 'sa',
    'mes', 'tes', 'ses', 'nos', 'vos', 'leurs', 'je', 'tu', 'il', 'elle',
    'nous', 'vous', 'ils', 'elles', 'me', 'te', 'se', 'lui', 'y', 'en',
    'qui', 'que', 'quoi', 'dont', 'où', 'quand', 'comment', 'pourquoi',
    'combien', 'est', 'sont', 'a', 'ont', 'avoir', 'être', 'faire', 'aller',
    'voir', 'savoir', 'pouvoir', 'falloir', 'vouloir', 'venir', 'prendre',
    'donner', 'passer', 'trouver', 'rendre', 'mettre', 'tenir', 'porter',
    'parler', 'aimer', 'sembler', 'laisser', 'suivre', 'entendre', 'regarder',
    'sentir', 'attendre', 'appeler', 'entrer', 'rester', 'revenir', 'partir',
    'devenir', 'recevoir', 'vivre', 'mourir', 'tenir', 'servir', 'suffire',
    'plaire', 'connaître', 'croire', 'boire', 'lire', 'dire', 'écrire',
    'rire', 'craindre', 'peindre', 'joindre', 'atteindre', 'teindre',
    'vaincre', 'convaincre', 'séduire', 'conduire', 'construire',
    'instruire', 'cuire', 'luire', 'nuire', 'plaire', 'taire', 'satisfaire',
    'traduire', 'produire', 'introduire', 'réduire', 'conduire',
    'moi', 'toi', 'soi', 'eux', 'lui', 'leur', 'celui', 'celle', 'ceux',
    'celles', 'ci', 'là', 'voici', 'voilà', 'ici', 'ailleurs', 'partout',
    'tout', 'tous', 'toute', 'toutes', 'aucun', 'aucune', 'nul', 'nulle',
    'plusieurs', 'certains', 'certaines', 'tel', 'telle', 'tels', 'telles',
    'autre', 'autres', 'même', 'mêmes', 'tel', 'telle', 'tels', 'telles',
    'quel', 'quelle', 'quels', 'quelles', 'quiconque', 'quoi', 'quoi',
    'lequel', 'laquelle', 'lesquels', 'lesquelles', 'duquel', 'desquels',
    'desquelles', 'auquel', 'auxquels', 'auxquelles', 'dont', 'où',
    'quand', 'comment', 'pourquoi', 'combien', 'que', 'qui', 'quoi',
    'lequel', 'laquelle', 'lesquels', 'lesquelles', 'duquel', 'desquels',
    'desquelles', 'auquel', 'auxquels', 'auxquelles', 'dont', 'où',
    'quand', 'comment', 'pourquoi', 'combien', 'que', 'qui', 'quoi',
}


class NLPPipeline:
    """Pipeline de prétraitement NLP pour le chatbot"""

    def __init__(self):
        self.lemmatizer = None
        self.stop_words = STOP_WORDS_FR

        if nltk_available:
            try:
                self.lemmatizer = WordNetLemmatizer()
                # Télécharger les ressources NLTK si nécessaire
                try:
                    self.stop_words = set(stopwords.words('french'))
                except LookupError:
                    nltk.download('stopwords', quiet=True)
                    self.stop_words = set(stopwords.words('french'))

                try:
                    nltk.data.find('tokenizers/punkt')
                except LookupError:
                    nltk.download('punkt', quiet=True)

                try:
                    nltk.data.find('corpora/wordnet')
                except LookupError:
                    nltk.download('wordnet', quiet=True)

            except Exception as e:
                logger.warning(f"NLTK initialization failed: {e}")
                self.lemmatizer = None

    def preprocess(self, text: str) -> str:
        """
        Pipeline complet : minuscules → ponctuation → tokenisation → 
        lemmatisation → stop words
        """
        # Minuscules
        text = text.lower()

        # Suppression ponctuation et chiffres
        text = re.sub(r'[^a-zA-Zàâäéèêëïîôöùûüç\s]', ' ', text)

        # Tokenisation simple (fallback si NLTK punkt non dispo)
        tokens = text.split()

        # Lemmatisation
        if self.lemmatizer:
            tokens = [self.lemmatizer.lemmatize(token) for token in tokens]

        # Suppression stop words
        tokens = [t for t in tokens if t not in self.stop_words and len(t) > 2]

        return ' '.join(tokens)


class ChatbotEngine:
    """
    Moteur de chatbot analytique avec VotingClassifier.

    Architecture (mémoire §4.3.4):
    - SVM (kernel=linear) pour frontières claires
    - Random Forest (n_estimators=100) pour robustesse
    - Régression Logistique pour probabilités calibrées
    """

    INTENTS = [
        'kpi_request', 'comparison_request', 'trend_request',
        'anomaly_request', 'product_request', 'category_request',
        'greeting', 'fallback'
    ]

    def __init__(self, model_path: str = None):
        self.nlp = NLPPipeline()
        self.vectorizer = None
        self.classifier = None
        self.model_path = model_path or 'chatbot_model.pkl'
        self.is_trained = False

        # Corpus par défaut (300 phrases, 6 intentions principales)
        self.corpus = self._build_default_corpus()

    def _build_default_corpus(self) -> list:
        """Corpus d'entraînement initial (mémoire §4.3.3)"""
        corpus = []

        # KPI Request
        kpi_phrases = [
            "quel est le chiffre d'affaires", "montre moi le CA", "combien on a vendu",
            "total des ventes", "revenu total", "chiffre d'affaires du mois",
            "CA par région", "ventes globales", "bilan commercial", "performance des ventes",
            "combien de commandes", "nombre de ventes", "statistiques de vente",
            "kpi ventes", "indicateur commercial", "tableau de bord ventes",
            "résultats financiers", "revenu généré", "profit total", "marge globale",
            "panier moyen", "valeur moyenne des commandes", "ticket moyen",
            "combien rapporte", "gains totaux", "recettes", "bénéfices",
        ]
        for p in kpi_phrases:
            corpus.append((p, 'kpi_request'))

        # Comparison Request
        comp_phrases = [
            "compare les ventes", "comparaison par région", "différence entre",
            "versus", "par rapport à", "en comparaison avec", "qui vend le plus",
            "quel commercial performe mieux", "région la plus performante",
            "comparer les catégories", "confrontation des résultats",
            "benchmark", "analyse comparative", "écart entre", "ratio de performance",
            "comparer ce mois et le mois dernier", "évolution par rapport à",
            "comparaison inter-régions", "duel commercial", "classement des vendeurs",
        ]
        for p in comp_phrases:
            corpus.append((p, 'comparison_request'))

        # Trend Request
        trend_phrases = [
            "tendance des ventes", "évolution du CA", "courbe de progression",
            "graphique temporel", "série chronologique", "prévisions de vente",
            "forecast", "projection", "tendance à la hausse", "baisse des ventes",
            "saisonnalité", "pic de vente", "variation mensuelle", "croissance",
            "décroissance", "évolution annuelle", "comparaison inter-annuelle",
            "tendance sur 6 mois", "analyse temporelle", "historique des ventes",
        ]
        for p in trend_phrases:
            corpus.append((p, 'trend_request'))

        # Anomaly Request
        anomaly_phrases = [
            "détecter anomalies", "ventes anormales", "outliers", "comportement suspect",
            "alerte", "alertes", "seuil dépassé", "seuil critique", "seuil d'alerte",
            "anomalie détectée", "valeur aberrante", "écart type", "fraude",
            "irrégularité", "incohérence", "données suspectes", "point de vigilance",
            "alerte rouge", "seuil de tolérance", "détection automatique",
        ]
        for p in anomaly_phrases:
            corpus.append((p, 'anomaly_request'))

        # Product Request
        prod_phrases = [
            "info sur produit", "détail article", "caractéristiques produit",
            "prix article", "stock disponible", "référence produit",
            "quel est le prix de", "disponibilité", "article en rupture",
            "produit le plus vendu", "top produit", "produit star",
            "référence", "code article", "désignation", "produit fantôme",
            "produit caché", "performance article", "marge par produit",
        ]
        for p in prod_phrases:
            corpus.append((p, 'product_request'))

        # Category Request
        cat_phrases = [
            "catégorie", "catégories", "rayon", "département", "famille produit",
            "segment", "classement par catégorie", "ventes par catégorie",
            "performance catégorielle", "répartition par type", "part de marché",
            "catégorie la plus vendue", "top catégorie", "catégorie en croissance",
            "diversification", "mix produit", "assortiment", "gamme",
        ]
        for p in cat_phrases:
            corpus.append((p, 'category_request'))

        # Greeting
        greet_phrases = [
            "bonjour", "salut", "hello", "coucou", "bonsoir", "comment ça va",
            "ça va", "hey", "hi", "bonjour jumia", "salut bot", "coucou assistant",
        ]
        for p in greet_phrases:
            corpus.append((p, 'greeting'))

        # Fallback (intentions non reconnues)
        fallback_phrases = [
            "météo", "heure", "blague", "raconte moi", "qui es-tu", "merci",
            "au revoir", "à plus", "ciao", "bye", "ok", "d'accord", " compris",
        ]
        for p in fallback_phrases:
            corpus.append((p, 'fallback'))

        return corpus

    def train(self, custom_corpus: list = None) -> dict:
        """
        Entraîne le VotingClassifier avec le corpus.
        Retourne les métriques de performance.
        """
        corpus = custom_corpus or self.corpus

        if len(corpus) < 10:
            raise ValueError("Corpus trop petit pour l'entraînement")

        # Prétraitement
        texts = [self.nlp.preprocess(p[0]) for p in corpus]
        labels = [p[1] for p in corpus]

        # Vectorisation TF-IDF avec n-grams (1-3)
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 3),
            max_features=5000,
            min_df=1,
            max_df=0.95,
            sublinear_tf=True
        )
        X = self.vectorizer.fit_transform(texts)

        # Split train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, labels, test_size=0.2, random_state=42, stratify=labels
        )

        # VotingClassifier (mémoire §4.3.4)
        svm = SVC(kernel='linear', probability=True, C=1.0, random_state=42)
        rf = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
        lr = LogisticRegression(max_iter=1000, random_state=42, C=1.0)

        self.classifier = VotingClassifier(
            estimators=[
                ('svm', svm),
                ('rf', rf),
                ('lr', lr)
            ],
            voting='soft'  # Utilise les probabilités pour vote pondéré
        )

        # Entraînement
        self.classifier.fit(X_train, y_train)

        # Évaluation
        y_pred = self.classifier.predict(X_test)
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

        self.is_trained = True

        logger.info(f"Chatbot entraîné - Accuracy: {accuracy:.3f}")

        return {
            'accuracy': accuracy,
            'classification_report': report,
            'n_samples': len(corpus),
            'n_features': X.shape[1]
        }

    def predict_intent(self, message: str) -> dict:
        """
        Prédit l'intention d'un message avec score de confiance.
        Retourne : {'intent': str, 'confidence': float, 'all_probs': dict}
        """
        if not self.is_trained:
            raise RuntimeError("Le modèle n'est pas entraîné. Appelez train() d'abord.")

        # Prétraitement
        processed = self.nlp.preprocess(message)

        if not processed.strip():
            return {
                'intent': 'fallback',
                'confidence': 1.0,
                'all_probs': {intent: 0.0 for intent in self.INTENTS}
            }

        # Vectorisation
        X = self.vectorizer.transform([processed])

        # Prédiction
        intent = self.classifier.predict(X)[0]

        # Probabilités
        try:
            probs = self.classifier.predict_proba(X)[0]
            all_probs = dict(zip(self.classifier.classes_, probs))
            confidence = max(probs)
        except AttributeError:
            # Fallback si predict_proba non dispo
            confidence = 0.8
            all_probs = {intent: 0.8}

        # Seuil de confiance (mémoire §4.3.5 : fallback intelligent)
        if confidence < 0.4:
            intent = 'fallback'

        return {
            'intent': intent,
            'confidence': float(confidence),
            'all_probs': {k: float(v) for k, v in all_probs.items()}
        }

    def generate_response(self, message: str, intent_data: dict = None) -> dict:
        """
        Génère une réponse SQL paramétrée selon l'intention détectée.
        Aligné avec le mémoire §4.3.6.
        """
        if intent_data is None:
            intent_data = self.predict_intent(message)

        intent = intent_data['intent']
        confidence = intent_data['confidence']

        # Templates de réponses et SQL
        responses = {
            'kpi_request': {
                'text': "Voici les indicateurs cles de performance demandes :",
                'sql_template': "SELECT SUM(ca_ligne) as chiffre_affaires, COUNT(DISTINCT commande_id) as nombre_commandes, AVG(ca_ligne) as panier_moyen, SUM(marge_ligne) as marge_totale FROM fait_ligne_commande fl JOIN fait_commande fc ON fl.commande_id = fc.id_commande WHERE fc.date_commande BETWEEN %(date_debut)s AND %(date_fin)s",
                'viz_type': 'kpi_cards'
            },
            'comparison_request': {
                'text': "Voici la comparaison demandee :",
                'sql_template': "SELECT c.nom_categorie, SUM(fl.ca_ligne) as ca, SUM(fl.marge_ligne) as marge FROM fait_ligne_commande fl JOIN dim_produit p ON fl.produit_id = p.id_produit JOIN dim_categorie c ON p.categorie_id = c.id_categorie GROUP BY c.nom_categorie ORDER BY ca DESC",
                'viz_type': 'bar_chart'
            },
            'trend_request': {
                'text': "Voici l'evolution temporelle :",
                'sql_template': "SELECT annee, mois, SUM(ca_ligne) as ca_mensuel FROM fait_ligne_commande fl JOIN fait_commande fc ON fl.commande_id = fc.id_commande GROUP BY annee, mois ORDER BY annee, mois",
                'viz_type': 'line_chart'
            },
            'anomaly_request': {
                'text': "Anomalies detectees dans les donnees :",
                'sql_template': "SELECT p.nom_article, SUM(fl.ca_ligne) as ca, AVG(fl.ca_ligne) as ca_moyen FROM fait_ligne_commande fl JOIN dim_produit p ON fl.produit_id = p.id_produit GROUP BY p.nom_article HAVING SUM(fl.ca_ligne) > 3 * AVG(fl.ca_ligne) OR SUM(fl.ca_ligne) < 0.1 * AVG(fl.ca_ligne)",
                'viz_type': 'alert_table'
            },
            'product_request': {
                'text': "Informations sur le produit :",
                'sql_template': "SELECT p.code_article, p.nom_article, p.prix_unitaire, p.stock_disponible, c.nom_categorie, SUM(fl.ca_ligne) as ca_total, SUM(fl.quantite) as quantite_vendue FROM dim_produit p JOIN dim_categorie c ON p.categorie_id = c.id_categorie LEFT JOIN fait_ligne_commande fl ON p.id_produit = fl.produit_id WHERE p.nom_article ILIKE %(search_term)s GROUP BY p.id_produit, c.nom_categorie",
                'viz_type': 'product_card'
            },
            'category_request': {
                'text': "Analyse par categorie :",
                'sql_template': "SELECT c.nom_categorie, COUNT(DISTINCT p.id_produit) as nb_produits, SUM(fl.ca_ligne) as ca_categorie, SUM(fl.marge_ligne) as marge_categorie FROM dim_categorie c JOIN dim_produit p ON c.id_categorie = p.categorie_id LEFT JOIN fait_ligne_commande fl ON p.id_produit = fl.produit_id GROUP BY c.nom_categorie ORDER BY ca_categorie DESC",
                'viz_type': 'pie_chart'
            },
            'greeting': {
                'text': "Bonjour ! Je suis Jumia Analytics Bot. Je peux vous aider avec :\n• KPIs et indicateurs commerciaux\n• Comparaisons et benchmarks\n• Tendances et previsions\n• Detection d'anomalies\n• Informations produits et categories\n\nQue souhaitez-vous analyser aujourd'hui ?",
                'sql_template': None,
                'viz_type': 'text'
            },
            'fallback': {
                'text': "Je n'ai pas compris votre demande. Essayez :\n• Quel est le CA du mois ?\n• Compare les ventes par region\n• Montre moi les tendances\n• Detecte les anomalies",
                'sql_template': None,
                'viz_type': 'text'
            }
        }

        response = responses.get(intent, responses['fallback'])
        response['intent'] = intent
        response['confidence'] = confidence

        return response

    def save_model(self, path: str = None):
        """Sauvegarde le modèle entraîné (joblib/pickle)"""
        path = path or self.model_path
        model_data = {
            'vectorizer': self.vectorizer,
            'classifier': self.classifier,
            'is_trained': self.is_trained,
            'intents': self.INTENTS
        }
        with open(path, 'wb') as f:
            pickle.dump(model_data, f)
        logger.info(f"Modèle sauvegardé: {path}")

    def load_model(self, path: str = None):
        """Charge un modèle pré-entraîné"""
        path = path or self.model_path
        if os.path.exists(path):
            with open(path, 'rb') as f:
                model_data = pickle.load(f)
            self.vectorizer = model_data['vectorizer']
            self.classifier = model_data['classifier']
            self.is_trained = model_data['is_trained']
            self.INTENTS = model_data.get('intents', self.INTENTS)
            logger.info(f"Modèle chargé: {path}")
            return True
        return False


# Singleton global
_chatbot_instance = None

def get_chatbot() -> ChatbotEngine:
    """Retourne l'instance singleton du chatbot"""
    global _chatbot_instance
    if _chatbot_instance is None:
        _chatbot_instance = ChatbotEngine()
        # Tente de charger un modèle existant
        if not _chatbot_instance.load_model():
            # Sinon entraîne avec le corpus par défaut
            _chatbot_instance.train()
            _chatbot_instance.save_model()
    return _chatbot_instance
