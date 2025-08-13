# apps/scheduling/tests.py

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch

from apps.accounts.models import User
from apps.learning.models import Course, Topic, Subtopic
from apps.scheduling.models import StudyPlan

class SchedulingAPITests(APITestCase):

    def setUp(self):
        """
        Configuração inicial para os testes, criando usuário, curso, tópico e subtópicos.
        """
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.client.force_authenticate(user=self.user)
        
        self.course = Course.objects.create(user=self.user, title="Engenharia de Software")
        self.topic = Topic.objects.create(course=self.course, title="Metodologias Ágeis")
        
        # Criamos subtópicos manualmente para usar no teste de geração de cronograma
        self.subtopic1 = Subtopic.objects.create(topic=self.topic, title="Scrum", order=0)
        self.subtopic2 = Subtopic.objects.create(topic=self.topic, title="Kanban", order=1)

    def test_create_and_list_study_plan(self):
        """
        Garante que um usuário pode criar uma meta de estudo e depois listá-la.
        """
        # --- Teste de Criação ---
        create_url = reverse('studyplan-list') # A URL do ViewSet para POST e GET (lista)
        data = {
            "course": self.course.id,
            "day_of_week": 0,  # Segunda-feira
            "minutes_planned": 90
        }

        # Ação de Criação
        response_create = self.client.post(create_url, data, format='json')

        # Verificação da Criação
        self.assertEqual(response_create.status_code, status.HTTP_201_CREATED)
        self.assertEqual(StudyPlan.objects.count(), 1)
        
        plan = StudyPlan.objects.first()
        self.assertEqual(plan.user, self.user)
        self.assertEqual(plan.course, self.course)
        self.assertEqual(plan.minutes_planned, 90)

        # --- Teste de Listagem ---
        # Ação de Listagem
        response_list = self.client.get(create_url)

        # Verificação da Listagem
        self.assertEqual(response_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response_list.data), 1)
        self.assertEqual(response_list.data[0]['minutes_planned'], 90)
        self.assertEqual(response_list.data[0]['day_of_week_display'], 'Segunda-feira')

    @patch('apps.core.services.deepseek_service.distribuir_subtopicos_no_cronograma')
    def test_generate_schedule_flow(self, mock_distribuir_subtopicos):
        """
        Testa o endpoint de geração de cronograma, mockando a chamada à IA.
        """
        # Preparação 1: Criar as metas de estudo (StudyPlan) que a IA vai usar
        StudyPlan.objects.create(user=self.user, course=self.course, day_of_week=0, minutes_planned=60) # Seg
        StudyPlan.objects.create(user=self.user, course=self.course, day_of_week=2, minutes_planned=60) # Qua

        # Preparação 2: Definir o que a função mockada da IA deve retornar
        mock_distribuir_subtopicos.return_value = {
            "Segunda-feira": [
                {"subtopic": "Scrum", "estimated_time": 45, "difficulty": "Médio"}
            ],
            "Terça-feira": [],
            "Quarta-feira": [
                {"subtopic": "Kanban", "estimated_time": 30, "difficulty": "Fácil"}
            ],
            "Quinta-feira": [],
            "Sexta-feira": [],
            "Sábado": [],
            "Domingo": []
        }

        url = reverse('generate-schedule')
        data = {"topic_id": self.topic.id}

        # Ação
        response = self.client.post(url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verifica se a função da IA foi chamada com os argumentos corretos
        # Pegamos os planos de estudo e subtópicos para garantir que a view os passou corretamente
        planos_de_estudo = list(StudyPlan.objects.filter(user=self.user, course=self.course))
        subtopicos_titulos = list(self.topic.subtopics.values_list('title', flat=True).order_by('order'))
        
        mock_distribuir_subtopicos.assert_called_once()
        # Verificamos a chamada da função mockada. É um pouco complexo, mas garante que a view está funcionando.
        # O primeiro argumento da chamada é 'args', o segundo é 'kwargs'.
        call_args, call_kwargs = mock_distribuir_subtopicos.call_args
        self.assertEqual(call_kwargs['topico'], self.topic)
        self.assertListEqual(call_kwargs['subtopicos'], subtopicos_titulos)
        self.assertListEqual(call_kwargs['planos_de_estudo'], planos_de_estudo)

        # Verifica se a resposta da API é exatamente o que a IA retornou
        self.assertEqual(response.data['Segunda-feira'][0]['subtopic'], "Scrum")
        self.assertEqual(len(response.data['Terça-feira']), 0)

    def test_generate_schedule_without_study_plan(self):
        """
        Garante que o endpoint retorna um erro se o usuário não tiver metas de estudo definidas.
        """
        # Preparação: NENHUM StudyPlan é criado.
        
        url = reverse('generate-schedule')
        data = {"topic_id": self.topic.id}

        # Ação
        response = self.client.post(url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Você precisa definir um plano de estudo", response.data['error'])

