# apps/analytics/tests.py

import datetime
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
import numpy as np # Usaremos numpy para o cálculo da correlação no teste

from apps.accounts.models import User
from apps.learning.models import Course, Topic
from apps.scheduling.models import StudyLog
from apps.assessment.models import Quiz, Attempt

class AnalyticsAPITests(APITestCase):

    def setUp(self):
        """
        Configuração inicial para os testes.
        """
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.client.force_authenticate(user=self.user)
        self.url = reverse('analytics-study-effectiveness')

    def _create_full_topic_data(self, topic_title, minutes_studied, quiz_score):
        """
        Função auxiliar para criar um conjunto completo de dados (Tópico, Log, Quiz, Tentativa)
        para um único ponto de dados na nossa análise.
        """
        course, _ = Course.objects.get_or_create(user=self.user, title="Matemática Discreta")
        topic = Topic.objects.create(course=course, title=topic_title)
        
        # Cria o log de estudo
        StudyLog.objects.create(
            user=self.user,
            course=course,
            topic=topic,
            date=datetime.date.today(),
            minutes_studied=minutes_studied
        )
        
        # Cria o quiz e a tentativa
        quiz = Quiz.objects.create(topic=topic, title=f"Quiz de {topic_title}")
        Attempt.objects.create(
            user=self.user,
            quiz=quiz,
            score=quiz_score
        )
        return topic

    def test_study_effectiveness_strong_positive_correlation(self):
        """
        Testa o cálculo de correlação com dados que devem resultar em uma correlação positiva forte.
        """
        # Preparação: Criar dados com uma correlação clara
        # Tópico 1: Pouco estudo, nota baixa
        self._create_full_topic_data("Teoria dos Grafos", minutes_studied=30, quiz_score=55.0)
        # Tópico 2: Estudo médio, nota média
        self._create_full_topic_data("Lógica Proposicional", minutes_studied=90, quiz_score=75.0)
        # Tópico 3: Muito estudo, nota alta
        self._create_full_topic_data("Relações de Recorrência", minutes_studied=180, quiz_score=95.0)

        # Ação
        response = self.client.get(self.url)

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        self.assertEqual(data['data_points'], 3)
        self.assertIn("forte e positiva", data['interpretation'])
        
        # Verificação do cálculo
        # Usamos numpy para recalcular a correlação aqui no teste e comparar.
        tempos = [30, 90, 180]
        notas = [55.0, 75.0, 95.0]
        expected_correlation = np.corrcoef(tempos, notas)[0, 1]
        
        # Usamos assertAlmostEqual para lidar com pequenas imprecisões de ponto flutuante
        self.assertAlmostEqual(data['correlation_coefficient'], expected_correlation, places=5)
        self.assertEqual(len(data['topic_data']), 3)

    def test_study_effectiveness_no_data(self):
        """
        Testa o comportamento do endpoint quando não há dados suficientes para a análise.
        """
        # Preparação: Apenas um tópico com dados. Correlação não pode ser calculada.
        self._create_full_topic_data("Conjuntos", minutes_studied=60, quiz_score=80.0)

        # Ação
        response = self.client.get(self.url)

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        self.assertIsNone(data['correlation_coefficient'])
        self.assertEqual(data['data_points'], 1)
        self.assertIn("São necessários pelo menos dois tópicos", data['interpretation'])

    def test_study_effectiveness_ignores_incomplete_data(self):
        """
        Garante que a análise ignora tópicos que não têm tanto logs de estudo quanto notas de quiz.
        """
        # Preparação
        # Tópico 1: Dados completos (será o único incluído na análise)
        self._create_full_topic_data("Permutações", minutes_studied=45, quiz_score=88.0)
        # Tópico 2: Dados completos (será o segundo incluído na análise)
        self._create_full_topic_data("Combinações", minutes_studied=75, quiz_score=92.0)
        
        # Tópico 3: Tem estudo, mas não tem nota de quiz
        course = Course.objects.get(title="Matemática Discreta")
        topic_sem_quiz = Topic.objects.create(course=course, title="Tópico Sem Quiz")
        StudyLog.objects.create(user=self.user, course=course, topic=topic_sem_quiz, date=datetime.date.today(), minutes_studied=100)

        # Tópico 4: Tem quiz, mas não tem log de estudo
        topic_sem_estudo = Topic.objects.create(course=course, title="Tópico Sem Estudo")
        quiz = Quiz.objects.create(topic=topic_sem_estudo, title="Quiz Inútil")
        Attempt.objects.create(user=self.user, quiz=quiz, score=50.0)

        # Ação
        response = self.client.get(self.url)

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        data = response.data
        # Apenas 2 dos 4 tópicos devem ser usados no cálculo
        self.assertEqual(data['data_points'], 2)
        self.assertIsNotNone(data['correlation_coefficient'])
        self.assertEqual(len(data['topic_data']), 2)
        
        # Verifica se os tópicos corretos foram usados
        included_topics = [d['topic_title'] for d in data['topic_data']]
        self.assertIn("Permutações", included_topics)
        self.assertIn("Combinações", included_topics)
        self.assertNotIn("Tópico Sem Quiz", included_topics)
        self.assertNotIn("Tópico Sem Estudo", included_topics)

