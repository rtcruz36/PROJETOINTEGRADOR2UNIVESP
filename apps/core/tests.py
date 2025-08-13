# apps/core/tests.py

# apps/core/tests.py

import json as _json
from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from apps.learning.models import Course, Topic, Subtopic
from apps.scheduling.models import StudyPlan
from apps.core.services import deepseek_service as ds

User = get_user_model()

class DeepseekServiceMoreEdges(TestCase):
    @patch("apps.core.services.deepseek_service.requests.post")
    def test__safe_post_timeout_returns_safe_error_response(self, mock_post):
        # Força Timeout para entrar no except do _safe_post
        import requests
        mock_post.side_effect = requests.Timeout("boom")

        resp = ds._safe_post("http://example.com", headers={}, json={}, timeout=1)

        # Exercita os métodos do _SafeErrorResponse explicitamente:
        self.assertEqual(resp.status_code, 503)
        self.assertFalse(resp.ok)           # @property ok
        self.assertEqual(resp.json(), {})   # .json()
        # .raise_for_status() é no-op — não deve levantar
        resp.raise_for_status()

    @patch("apps.core.services.deepseek_service._safe_post")
    def test__call_deepseek_api_includes_response_format_when_json_output_true(self, mock_safe_post):
        # Retorno OK fake
        class _Resp:
            def raise_for_status(self): return
            def json(self): return {"choices": [{"message": {"content": "{}"}}]}
        mock_safe_post.return_value = _Resp()

        _ = ds._call_deepseek_api("qualquer", is_json_output=True)

        # Verifica que o payload enviado ao _safe_post tem response_format
        sent = mock_safe_post.call_args.kwargs["json"]
        assert "response_format" in sent
        assert sent["response_format"] == {"type": "json_object"}

    @patch("apps.core.services.deepseek_service._call_deepseek_api")
    def test_distribuir_subtopicos_empty_analysis_returns_empty(self, mock_api_call):
        # JSON válido, mas com lista vazia -> cobre o `if not subtopicos_analizados: return {}`
        mock_api_call.return_value = {
            "choices": [{
                "message": {"content": _json.dumps({"analise_subtopicos": []})}
            }]
        }


# -----------------------------------------------------------
# Fakes para simular respostas da API DeepSeek
# -----------------------------------------------------------

class FakeResponseOK:
    status_code = 200
    reason = "OK"

    def raise_for_status(self):
        return

    def json(self):
        # Estrutura mínima que o código usa
        return {"choices": [{"message": {"content": "CONTEUDO_OK"}}]}


class FakeResponseBadJSON:
    status_code = 200
    reason = "OK"

    def raise_for_status(self):
        return

    def json(self):
        # Simula JSON inválido
        raise ValueError("No JSON object could be decoded")


class FakeResponseHTTPError:
    status_code = 500
    reason = "Internal Server Error"

    def raise_for_status(self):
        from requests import HTTPError
        raise HTTPError("500 Server Error")

    def json(self):
        return {}


class LocalSafeErrorResponse:
    """Espelha o _SafeErrorResponse do serviço: .json() -> {}, raise_for_status() no-op"""
    status_code = 503
    reason = "Service Unavailable"

    def raise_for_status(self):
        return

    def json(self):
        return {}

    @property
    def ok(self):
        return False


class TestDeepSeekAPI(TestCase):
    """
    Testes para as funções do serviço DeepSeek API,
    alinhados ao comportamento atual (Opção 1).
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        self.course = Course.objects.create(
            user=self.user,
            title="Cálculo I",
            description="Curso de cálculo diferencial"
        )

        self.topic = Topic.objects.create(
            title="Derivadas",
            course=self.course,
            order=1
        )

        self.subtopics = [
            Subtopic.objects.create(topic=self.topic, title="Conceito de Derivada", order=1),
            Subtopic.objects.create(topic=self.topic, title="Regras de Derivação", order=2),
        ]

        self.study_plan = StudyPlan.objects.create(
            user=self.user, course=self.course, day_of_week=0, minutes_planned=60
        )

    # --- Testes para _call_deepseek_api ---

    @patch('apps.core.services.deepseek_service._safe_post', return_value=FakeResponseOK())
    def test_call_deepseek_api_success(self, mock_post):
        result = ds._call_deepseek_api("Teste prompt")
        self.assertIsInstance(result, dict)
        self.assertIn('choices', result)
        # garante que montou o payload com messages
        called_kwargs = mock_post.call_args.kwargs
        self.assertIn('json', called_kwargs)
        self.assertIn('messages', called_kwargs['json'])

    @patch('apps.core.services.deepseek_service._safe_post', return_value=LocalSafeErrorResponse())
    def test_call_deepseek_api_network_error_retorna_dict_vazio(self, mock_post):
        result = ds._call_deepseek_api("Teste prompt")
        self.assertEqual(result, {})  # novo contrato: não levanta, retorna {}

    @patch('apps.core.services.deepseek_service._safe_post', return_value=FakeResponseBadJSON())
    def test_call_deepseek_api_json_invalido_retorna_dict_vazio(self, mock_post):
        result = ds._call_deepseek_api("Teste prompt")
        self.assertEqual(result, {})  # novo contrato: não levanta, retorna {}

    @patch('apps.core.services.deepseek_service._safe_post', return_value=FakeResponseHTTPError())
    def test_call_deepseek_api_http_erro_retorna_dict_vazio(self, mock_post):
        result = ds._call_deepseek_api("Teste prompt")
        self.assertEqual(result, {})  # raise_for_status falha → {}

    @patch('apps.core.services.deepseek_service.settings')
    def test_api_key_not_set(self, mock_settings):
        mock_settings.DEEPSEEK_API_KEY = None
        from apps.core.services.deepseek_service import HEADERS
        self.assertIn("Authorization", HEADERS)

    # --- Testes para sugerir_plano_de_topico ---

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_sugerir_plano_de_topico_success(self, mock_api_call):
        mock_api_call.return_value = {
            'choices': [{'message': {'content': '# Plano de Estudo\n\nConteúdo do plano...'}}]
        }
        result = ds.sugerir_plano_de_topico("Cálculo I", "Derivadas")
        self.assertEqual(result, '# Plano de Estudo\n\nConteúdo do plano...')
        mock_api_call.assert_called_once()

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_sugerir_plano_de_topico_api_error(self, mock_api_call):
        # Pode simular erro lançando ConnectionError...
        mock_api_call.side_effect = ConnectionError("Erro de rede")
        result = ds.sugerir_plano_de_topico("Cálculo I", "Derivadas")
        self.assertIn("Não foi possível gerar", result)

        # ... ou retornando dict vazio (equivalente ao novo contrato)
        mock_api_call.side_effect = None
        mock_api_call.return_value = {}
        result2 = ds.sugerir_plano_de_topico("Cálculo I", "Derivadas")
        self.assertIn("Não foi possível gerar", result2)

    # --- Testes para sugerir_subtopicos ---

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_sugerir_subtopicos_success(self, mock_api_call):
        mock_api_call.return_value = {
            'choices': [{'message': {'content': '{"subtopicos": ["Definição", "Regras", "Aplicações"]}'}}]
        }
        result = ds.sugerir_subtopicos(self.topic)
        self.assertEqual(result, ["Definição", "Regras", "Aplicações"])
        mock_api_call.assert_called_once()

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_sugerir_subtopicos_json_invalido(self, mock_api_call):
        mock_api_call.return_value = {'choices': [{'message': {'content': 'JSON inválido'}}]}
        result = ds.sugerir_subtopicos(self.topic)
        self.assertEqual(result, [])

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_sugerir_subtopicos_api_error(self, mock_api_call):
        # Erro como exceção
        mock_api_call.side_effect = ConnectionError("Erro de rede")
        self.assertEqual(ds.sugerir_subtopicos(self.topic), [])
        # Erro como {} (novo contrato)
        mock_api_call.side_effect = None
        mock_api_call.return_value = {}
        self.assertEqual(ds.sugerir_subtopicos(self.topic), [])

    # --- Testes para gerar_quiz_completo ---

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_gerar_quiz_completo_success(self, mock_api_call):
        quiz_json = {
            "quiz_title": "Quiz sobre Derivadas",
            "quiz_description": "Teste seus conhecimentos",
            "questions": [{
                "question_text": "O que é uma derivada?",
                "choices": {"A": "Opção A", "B": "Opção B", "C": "Opção C", "D": "Opção D"},
                "correct_answer": "A",
                "difficulty": "EASY",
                "explanation": "Explicação da resposta"
            }]
        }
        mock_api_call.return_value = {
            'choices': [{'message': {'content': json.dumps(quiz_json)}}]
        }
        result = ds.gerar_quiz_completo(self.topic)
        self.assertIsNotNone(result)
        self.assertIn("quiz_title", result)
        self.assertIn("questions", result)
        self.assertEqual(len(result["questions"]), 1)

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_gerar_quiz_completo_json_incompleto(self, mock_api_call):
        quiz_json = {"titulo": "Quiz incompleto"}  # faltam quiz_title e questions
        mock_api_call.return_value = {
            'choices': [{'message': {'content': json.dumps(quiz_json)}}]
        }
        self.assertIsNone(ds.gerar_quiz_completo(self.topic))

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_gerar_quiz_completo_api_error(self, mock_api_call):
        # Erro como exceção
        mock_api_call.side_effect = ConnectionError("Erro de rede")
        self.assertIsNone(ds.gerar_quiz_completo(self.topic))
        # Erro como {} (novo contrato)
        mock_api_call.side_effect = None
        mock_api_call.return_value = {}
        self.assertIsNone(ds.gerar_quiz_completo(self.topic))

    # --- Testes para responder_pergunta_de_estudo ---

    @patch('apps.core.services.deepseek_service._safe_post', return_value=FakeResponseOK())
    def test_responder_pergunta_de_estudo_success(self, mock_post):
        historico = [
            {"role": "user", "content": "Pergunta anterior"},
            {"role": "assistant", "content": "Resposta anterior"},
        ]
        result = ds.responder_pergunta_de_estudo("O que é uma derivada?", historico, self.topic)
        self.assertEqual(result, "CONTEUDO_OK")
        mock_post.assert_called_once()

    @patch('apps.core.services.deepseek_service._safe_post', return_value=LocalSafeErrorResponse())
    def test_responder_pergunta_de_estudo_error_network(self, mock_post):
        result = ds.responder_pergunta_de_estudo("O que é uma derivada?", [], self.topic)
        self.assertIn("Desculpe, não consegui processar sua pergunta no momento", result)

    @patch('apps.core.services.deepseek_service._safe_post', return_value=FakeResponseHTTPError())
    def test_responder_pergunta_de_estudo_http_error(self, mock_post):
        result = ds.responder_pergunta_de_estudo("O que é uma derivada?", [], self.topic)
        self.assertIn("Desculpe, não consegui processar sua pergunta no momento", result)

    @patch('apps.core.services.deepseek_service._safe_post', return_value=FakeResponseBadJSON())
    def test_responder_pergunta_de_estudo_json_invalido(self, mock_post):
        result = ds.responder_pergunta_de_estudo("O que é uma derivada?", [], self.topic)
        self.assertIn("Desculpe, não consegui processar sua pergunta no momento", result)

    # --- Testes para distribuir_subtopicos_no_cronograma ---

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_distribuir_subtopicos_no_cronograma_success(self, mock_api_call):
        analise_json = {
            "analise_subtopicos": [
                {"subtopic": "Conceito de Derivada", "estimated_time": 45, "difficulty": "Fácil"},
                {"subtopic": "Regras de Derivação", "estimated_time": 60, "difficulty": "Médio"},
            ]
        }
        mock_api_call.return_value = {
            'choices': [{'message': {'content': json.dumps(analise_json)}}]
        }
        subtopicos = ["Conceito de Derivada", "Regras de Derivação"]
        planos = [self.study_plan]
        result = ds.distribuir_subtopicos_no_cronograma(self.topic, subtopicos, planos)
        self.assertIsInstance(result, dict)
        self.assertIn("Segunda-feira", result)

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_distribuir_subtopicos_no_cronograma_sem_subtopicos(self, mock_api_call):
        result = ds.distribuir_subtopicos_no_cronograma(self.topic, [], [self.study_plan])
        self.assertEqual(result, {})
        mock_api_call.assert_not_called()

    @patch('apps.core.services.deepseek_service._call_deepseek_api')
    def test_distribuir_subtopicos_no_cronograma_api_error(self, mock_api_call):
        # Erro como exceção
        mock_api_call.side_effect = ConnectionError("Erro de rede")
        subtopicos = ["Conceito de Derivada", "Regras de Derivação"]
        result = ds.distribuir_subtopicos_no_cronograma(self.topic, subtopicos, [self.study_plan])
        self.assertEqual(result, {})
        # Erro como {} (novo contrato)
        mock_api_call.side_effect = None
        mock_api_call.return_value = {}
        result2 = ds.distribuir_subtopicos_no_cronograma(self.topic, subtopicos, [self.study_plan])
        self.assertEqual(result2, {})
