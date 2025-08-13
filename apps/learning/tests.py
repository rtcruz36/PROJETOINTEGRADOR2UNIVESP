# apps/learning/tests.py

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch # Ferramenta para "mockar"

from apps.accounts.models import User
from apps.learning.models import Course, Topic, Subtopic

class LearningAPITests(APITestCase):

    def setUp(self):
        """Configuração inicial para todos os testes nesta classe."""
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.client.force_authenticate(user=self.user) # Força a autenticação para não precisar fazer login sempre
        self.url = reverse('create-study-plan')

    # O decorador @patch substitui a função do deepseek_service durante o teste
    @patch('apps.core.services.deepseek_service.sugerir_subtopicos')
    @patch('apps.core.services.deepseek_service.sugerir_plano_de_topico')
    def test_create_study_plan_flow(self, mock_sugerir_plano, mock_sugerir_subtopicos):
        """
        Testa o endpoint principal de criação, garantindo que a IA é chamada
        e os objetos são criados corretamente.
        """
        # Preparação: Definimos o que as funções "mockadas" devem retornar
        mock_sugerir_plano.return_value = "Este é um plano de estudos detalhado."
        mock_sugerir_subtopicos.return_value = ["Subtópico 1", "Subtópico 2", "Subtópico 3"]

        data = {
            "course_title": "Física Quântica",
            "topic_title": "O Princípio da Incerteza",
            "course_description": "Uma introdução."
        }

        # Ação
        response = self.client.post(self.url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # Verifica se os objetos foram criados no banco
        self.assertTrue(Course.objects.filter(title="Física Quântica").exists())
        self.assertTrue(Topic.objects.filter(title="O Princípio da Incerteza").exists())
        self.assertEqual(Subtopic.objects.count(), 3)
        
        # Verifica se as funções da IA foram chamadas
        mock_sugerir_plano.assert_called_once()
        mock_sugerir_subtopicos.assert_called_once()

        # Verifica o conteúdo da resposta
        self.assertEqual(response.data['title'], "O Princípio da Incerteza")
        self.assertEqual(len(response.data['subtopics']), 3)
