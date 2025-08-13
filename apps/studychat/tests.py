# apps/studychat/tests.py

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch
from apps.accounts.models import User
from apps.learning.models import Course, Topic
from django.contrib.auth import get_user_model

User = get_user_model()


class StudyChatEdgesTests(APITestCase):
    def setUp(self):
        # usuário autenticado (dono)
        self.user = User.objects.create_user(
            username='owner', email='owner@example.com', password='p'
        )
        self.client.force_authenticate(self.user)

        # curso + tópico do dono (válidos)
        self.course = Course.objects.create(user=self.user, title="IA")
        self.topic = Topic.objects.create(course=self.course, title="CNN")

        # outro usuário + tópico (não pode ser usado pelo dono)
        other = User.objects.create_user(
            username='other', email='other@example.com', password='p'
        )
        other_course = Course.objects.create(user=other, title="Outro Curso")
        self.other_topic = Topic.objects.create(course=other_course, title="Outro Tópico")

        self.url = reverse('studychat-ask')

    def test_topic_id_de_outro_usuario_rejeitado_pelo_serializer(self):
        """Cobre o except do validate_topic_id (tópico não pertence ao usuário)."""
        data = {
            "question": "posso usar esse tópico?",
            "history": [],
            "topic_id": self.other_topic.id,  # não pertence ao usuário logado
        }
        resp = self.client.post(self.url, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # mensagem definida no serializer
        self.assertIn(
            "Tópico de contexto não encontrado ou não pertence a você",
            str(resp.data)
        )

    @patch("apps.core.services.deepseek_service.responder_pergunta_de_estudo", side_effect=Exception("boom"))
    def test_excecao_no_servico_retorna_500(self, _mock_ia):
        """Cobre o bloco except da view, retornando 500 com mensagem de erro."""
        data = {
            "question": "O que é backprop?",
            "history": [],
            "topic_id": self.topic.id,
        }
        resp = self.client.post(self.url, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        # chave e trecho de mensagem definidos na view
        self.assertIn("erro", resp.data)
        self.assertIn("processar sua pergunta", resp.data["erro"])


class StudyChatAPITests(APITestCase):

    def setUp(self):
        """
        Configuração inicial, criando um usuário e um tópico para contexto.
        """
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='password')
        self.client.force_authenticate(user=self.user)
        
        # Tópico que pode ser usado para dar contexto ao chat
        self.course = Course.objects.create(user=self.user, title="Inteligência Artificial")
        self.topic = Topic.objects.create(course=self.course, title="Redes Neurais Convolucionais (CNN)")
        
        self.url = reverse('studychat-ask')

    @patch('apps.core.services.deepseek_service.responder_pergunta_de_estudo')
    def test_ask_question_with_context(self, mock_responder_pergunta):
        """
        Testa o fluxo principal do chat, enviando uma pergunta com histórico e contexto de tópico.
        """
        # Preparação 1: Definir o que a função mockada da IA deve retornar
        mock_responder_pergunta.return_value = "Uma CNN é uma arquitetura de rede neural profunda usada principalmente para processar dados visuais."

        # Preparação 2: Montar os dados da requisição
        data = {
            "question": "O que é uma CNN?",
            "history": [
                {"role": "user", "content": "Olá, pode me ajudar com IA?"},
                {"role": "assistant", "content": "Claro! Sobre qual tópico?"}
            ],
            "topic_id": self.topic.id
        }

        # Ação
        response = self.client.post(self.url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Verifica se a resposta da API contém o que a IA retornou
        self.assertEqual(response.data['role'], 'assistant')
        self.assertEqual(response.data['content'], "Uma CNN é uma arquitetura de rede neural profunda usada principalmente para processar dados visuais.")

        # Verifica se a função da IA foi chamada com os argumentos corretos
        mock_responder_pergunta.assert_called_once()
        call_args, call_kwargs = mock_responder_pergunta.call_args
        
        self.assertEqual(call_kwargs['pergunta_usuario'], "O que é uma CNN?")
        self.assertEqual(len(call_kwargs['historico_conversa']), 2)
        self.assertEqual(call_kwargs['historico_conversa'][0]['role'], 'user')
        self.assertEqual(call_kwargs['topico_contexto'], self.topic)

    @patch('apps.core.services.deepseek_service.responder_pergunta_de_estudo')
    def test_ask_question_without_context(self, mock_responder_pergunta):
        """
        Testa o chat sem um tópico de contexto, o que também é um caso de uso válido.
        """
        # Preparação
        mock_responder_pergunta.return_value = "Django é um framework web de alto nível para Python."
        data = {
            "question": "O que é Django?",
            "history": [], # Primeira pergunta, histórico vazio
            "topic_id": None # Sem contexto
        }

        # Ação
        response = self.client.post(self.url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['content'], "Django é um framework web de alto nível para Python.")

        # Verifica a chamada da IA
        mock_responder_pergunta.assert_called_once_with(
            pergunta_usuario="O que é Django?",
            historico_conversa=[],
            topico_contexto=None
        )

    def test_ask_question_with_invalid_data(self):
        """
        Garante que o serializador rejeita dados malformados.
        """
        # Preparação: Dados inválidos (falta o campo 'history')
        data = {
            "question": "Isso vai falhar?"
        }

        # Ação
        response = self.client.post(self.url, data, format='json')

        # Verificação
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('history', response.data) # Verifica se o erro aponta para o campo ausente

