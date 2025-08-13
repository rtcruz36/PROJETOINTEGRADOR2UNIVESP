# tests/integration/test_assessment.py
import pytest
from django.urls import reverse
from rest_framework import status
from unittest.mock import patch

from apps.assessment.models import Quiz, Question, Attempt, Answer

@pytest.mark.django_db
class TestQuizGeneration:
    """Testes de geração de quiz com IA."""
    
    def test_generate_quiz_ai_failure(self, authenticated_client, topic):
        """Testa comportamento quando a IA falha ao gerar quiz."""
        with patch('apps.core.services.deepseek_service.gerar_quiz_completo') as mock:
            mock.return_value = None  # Simula falha da IA
            
            url = reverse('generate-quiz')
            data = {
                'topic_id': topic.id,
                'num_easy': 1,
                'num_moderate': 1,
                'num_hard': 1
            }
            
            response = authenticated_client.post(url, data, format='json')
            
            assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
            assert 'error' in response.data

@pytest.mark.django_db
class TestQuizViewSet:
    """Testes do ViewSet de Quizzes."""
    
    def test_list_user_quizzes(self, authenticated_client, quiz):
        """Testa listagem de quizzes do usuário."""
        url = reverse('quiz-list')
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['title'] == quiz.title

    def test_quiz_detail_with_questions(self, authenticated_client, quiz, questions):
        """Testa detalhes de um quiz com suas perguntas."""
        url = reverse('quiz-detail', args=[quiz.id])
        
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['title'] == quiz.title
        assert len(response.data['questions']) == len(questions)
        
        # Verifica que a resposta correta não é exposta
        for question in response.data['questions']:
            assert 'correct_answer' not in question
            assert 'explanation' not in question

    def test_user_cannot_see_other_user_quizzes(self, api_client, other_user, quiz):
        """Testa que usuário não vê quizzes de outros usuários."""
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(other_user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        url = reverse('quiz-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0

@pytest.mark.django_db
class TestAttemptSubmission:
    """Testes de submissão de tentativas de quiz."""
    
    def test_submit_attempt_success(self, authenticated_client, quiz, questions):
        """Testa submissão bem-sucedida de tentativa."""
        url = reverse('submit-attempt')
        data = {
            'quiz_id': quiz.id,
            'answers': [
                {'question_id': questions[0].id, 'user_answer': 'A'},  # Correto
                {'question_id': questions[1].id, 'user_answer': 'C'},  # Incorreto
            ]
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['score'] == 50.0  # 1 de 2 corretas
        assert response.data['correct_answers_count'] == 1
        assert response.data['incorrect_answers_count'] == 1
        assert len(response.data['answers']) == 2
        
        # Verifica se foi salvo no banco
        attempt = Attempt.objects.get(id=response.data['id'])
        assert attempt.quiz == quiz
        assert attempt.score == 50.0

    def test_submit_attempt_all_correct(self, authenticated_client, quiz, questions):
        """Testa submissão com todas as respostas corretas."""
        url = reverse('submit-attempt')
        data = {
            'quiz_id': quiz.id,
            'answers': [
                {'question_id': questions[0].id, 'user_answer': 'A'},  # Correto
                {'question_id': questions[1].id, 'user_answer': 'B'},  # Correto
            ]
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['score'] == 100.0
        assert response.data['correct_answers_count'] == 2
        assert response.data['incorrect_answers_count'] == 0

    def test_submit_attempt_all_incorrect(self, authenticated_client, quiz, questions):
        """Testa submissão com todas as respostas incorretas."""
        url = reverse('submit-attempt')
        data = {
            'quiz_id': quiz.id,
            'answers': [
                {'question_id': questions[0].id, 'user_answer': 'D'},  # Incorreto
                {'question_id': questions[1].id, 'user_answer': 'D'},  # Incorreto
            ]
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['score'] == 0.0
        assert response.data['correct_answers_count'] == 0
        assert response.data['incorrect_answers_count'] == 2

    def test_submit_attempt_partial_answers(self, authenticated_client, quiz, questions):
        """Testa submissão com apenas algumas respostas."""
        url = reverse('submit-attempt')
        data = {
            'quiz_id': quiz.id,
            'answers': [
                {'question_id': questions[0].id, 'user_answer': 'A'},  # Apenas uma resposta
            ]
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        # Score baseado apenas na pergunta respondida
        assert response.data['correct_answers_count'] == 1

    def test_submit_attempt_invalid_quiz(self, authenticated_client):
        """Testa submissão para quiz inexistente."""
        url = reverse('submit-attempt')
        data = {
            'quiz_id': 99999,
            'answers': [
                {'question_id': 1, 'user_answer': 'A'},
            ]
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_submit_attempt_empty_answers(self, authenticated_client, quiz):
        """Testa submissão com lista de respostas vazia."""
        url = reverse('submit-attempt')
        data = {
            'quiz_id': quiz.id,
            'answers': []
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_submit_attempt_case_insensitive(self, authenticated_client, quiz, questions):
        """Testa que a comparação de respostas é case-insensitive."""
        url = reverse('submit-attempt')
        data = {
            'quiz_id': quiz.id,
            'answers': [
                {'question_id': questions[0].id, 'user_answer': 'a'},  # Minúsculo
                {'question_id': questions[1].id, 'user_answer': 'b'},  # Minúsculo
            ]
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['score'] == 100.0  # Ambas corretas

@pytest.mark.django_db
class TestAttemptViewSet:
    """Testes do ViewSet de Tentativas."""
    
    def test_list_user_attempts(self, authenticated_client, user, quiz, questions):
        """Testa listagem de tentativas do usuário."""
        # Criar uma tentativa
        attempt = Attempt.objects.create(
            user=user,
            quiz=quiz,
            score=75.0,
            correct_answers_count=1,
            incorrect_answers_count=1
        )
        
        url = reverse('attempt-list')
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]['score'] == 75.0

    def test_attempt_detail_with_answers(self, authenticated_client, user, quiz, questions):
        """Testa detalhes de uma tentativa com respostas."""
        attempt = Attempt.objects.create(
            user=user,
            quiz=quiz,
            score=50.0,
            correct_answers_count=1,
            incorrect_answers_count=1
        )
        
        # Criar respostas
        Answer.objects.create(
            attempt=attempt,
            question=questions[0],
            user_answer='A',
            is_correct=True
        )
        Answer.objects.create(
            attempt=attempt,
            question=questions[1],
            user_answer='C',
            is_correct=False
        )
        
        url = reverse('attempt-detail', args=[attempt.id])
        response = authenticated_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['score'] == 50.0
        assert len(response.data['answers']) == 2

    def test_user_cannot_see_other_attempts(self, api_client, other_user, user, quiz):
        """Testa que usuário não vê tentativas de outros."""
        # Criar tentativa para outro usuário
        other_attempt = Attempt.objects.create(
            user=other_user,
            quiz=quiz,
            score=80.0,
            correct_answers_count=1,
            incorrect_answers_count=0
        )
        
        # Login como usuário original
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        url = reverse('attempt-list')
        response = api_client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 0

@pytest.mark.django_db
class TestAssessmentCompleteFlow:
    """Testes do fluxo completo de avaliação."""
    
    def test_complete_quiz_flow(self, authenticated_client, topic, mock_deepseek_quiz):
        """Testa o fluxo completo: gerar quiz -> fazer tentativa."""
        # 1. Gerar quiz
        generate_url = reverse('generate-quiz')
        generate_data = {
            'topic_id': topic.id,
            'num_easy': 1,
            'num_moderate': 1,
            'num_hard': 0
        }
        
        generate_response = authenticated_client.post(generate_url, generate_data, format='json')
        assert generate_response.status_code == status.HTTP_201_CREATED
        
        quiz_id = generate_response.data['id']
        questions = generate_response.data['questions']
        
        # 2. Submeter tentativa
        submit_url = reverse('submit-attempt')
        submit_data = {
            'quiz_id': quiz_id,
            'answers': [
                {'question_id': questions[0]['id'], 'user_answer': 'A'},
                {'question_id': questions[1]['id'], 'user_answer': 'B'},
            ]
        }
        
        submit_response = authenticated_client.post(submit_url, submit_data, format='json')
        assert submit_response.status_code == status.HTTP_201_CREATED
        
        # 3. Verificar tentativa salva
        attempt_id = submit_response.data['id']
        detail_url = reverse('attempt-detail', args=[attempt_id])
        detail_response = authenticated_client.get(detail_url)
        
        assert detail_response.status_code == status.HTTP_200_OK
        assert detail_response.data['score'] == submit_response.data['score']

    def test_generate_quiz_success(self, authenticated_client, topic, mock_deepseek_quiz):
        """Testa geração bem-sucedida de quiz."""
        url = reverse('generate-quiz')
        data = {
            'topic_id': topic.id,
            'num_easy': 1,
            'num_moderate': 1,
            'num_hard': 0
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert 'id' in response.data
        assert response.data['title'] == 'Quiz sobre Derivadas - Gerado por IA'
        assert len(response.data['questions']) == 2
        
        # Verifica se foi salvo no banco
        quiz = Quiz.objects.get(id=response.data['id'])
        assert quiz.topic == topic
        assert quiz.questions.count() == 2

    def test_generate_quiz_custom_difficulty_distribution(self, authenticated_client, topic, mock_deepseek_quiz):
        """Testa geração de quiz com distribuição customizada de dificuldade."""
        url = reverse('generate-quiz')
        data = {
            'topic_id': topic.id,
            'num_easy': 3,
            'num_moderate': 2,
            'num_hard': 1
        }
        
        # Simula resposta da IA com 6 perguntas
        mock_quiz_data = {
            'quiz_title': 'Quiz Customizado',
            'quiz_description': 'Quiz com distribuição customizada',
            'questions': [
                {
                    'question_text': f'Pergunta {i}',
                    'choices': {'A': 'Op1', 'B': 'Op2', 'C': 'Op3', 'D': 'Op4'},
                    'correct_answer': 'A',
                    'difficulty': 'EASY' if i <= 3 else ('MODERATE' if i <= 5 else 'HARD'),
                    'explanation': f'Explicação {i}'
                } for i in range(1, 7)
            ]
        }
        
        with patch('apps.core.services.deepseek_service.gerar_quiz_completo') as mock:
            mock.return_value = mock_quiz_data
            
            response = authenticated_client.post(url, data, format='json')
            
            assert response.status_code == status.HTTP_201_CREATED
            assert len(response.data['questions']) == 6

    def test_generate_quiz_invalid_topic(self, authenticated_client):
        """Testa geração de quiz para tópico inexistente."""
        url = reverse('generate-quiz')
        data = {
            'topic_id': 99999,  # ID inexistente
            'num_easy': 1,
            'num_moderate': 1,
            'num_hard': 1
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_generate_quiz_other_user_topic(self, api_client, other_user, topic):
        """Testa que usuário não pode gerar quiz para tópico de outro usuário."""
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(other_user)
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
        
        url = reverse('generate-quiz')
        data = {
            'topic_id': topic.id,
            'num_easy': 1,
            'num_moderate': 1,
            'num_hard': 1
        }
        
        response = api_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_generate_quiz_no_questions(self, authenticated_client, topic):
        """Testa geração de quiz sem perguntas."""
        url = reverse('generate-quiz')
        data = {
            'topic_id': topic.id,
            'num_easy': 0,
            'num_moderate': 0,
            'num_hard': 0
        }
        
        response = authenticated_client.post(url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
        assert response.data['error'] == 'Deve haver pelo menos uma pergunta no quiz.'