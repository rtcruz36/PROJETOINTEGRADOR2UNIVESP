# apps/assessment/views.py
import json
from rest_framework import viewsets, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404
import logging
import requests
from .models import Quiz, Question, Attempt, Answer
from .serializers import (
    QuizDetailSerializer, 
    AttemptDetailSerializer,
    QuizGenerationSerializer,
    AttemptSubmissionSerializer
)
from apps.core.services import deepseek_service
from apps.learning.models import Topic
from requests.exceptions import Timeout

logger = logging.getLogger(__name__)

class GenerateQuizView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            # Validar dados de entrada
            serializer = QuizGenerationSerializer(data=request.data, context={'request': request})
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
            validated_data = serializer.validated_data
            topic = validated_data['topic_id']  # Agora é o objeto Topic
            num_easy = validated_data.get('num_easy', 7)
            num_moderate = validated_data.get('num_moderate', 7)
            num_hard = validated_data.get('num_hard', 6)
            
            # Chamar serviço de IA
            quiz_data = deepseek_service.gerar_quiz_completo(
                topico=topic,
                num_faceis=num_easy,
                num_moderadas=num_moderate,
                num_dificeis=num_hard
            )
            
            if not quiz_data:
                logger.warning("Serviço gerar_quiz_completo retornou None ou dados inválidos.")
                return Response(
                    {"error": "Falha ao gerar conteúdo do quiz. Serviço indisponível."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            
            # Criar o quiz no banco de dados com transaction
            with transaction.atomic():
                quiz = Quiz.objects.create(
                    topic=topic,
                    title=quiz_data.get('quiz_title', f'Quiz sobre {topic.title}'),
                    description=quiz_data.get('quiz_description', ''),
                    total_questions=len(quiz_data.get('questions', []))
                )
                
                # Criar as perguntas
                questions_data = quiz_data.get('questions', [])
                for question_data in questions_data:
                    Question.objects.create(
                        quiz=quiz,
                        question_text=question_data['question_text'],
                        choices=question_data['choices'],
                        correct_answer=question_data['correct_answer'],
                        difficulty=question_data.get('difficulty', 'MODERATE'),
                        explanation=question_data.get('explanation', '')
                    )
            
            # Retornar o quiz criado
            serializer = QuizDetailSerializer(quiz)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
            
        except requests.exceptions.Timeout:
            logger.error("Timeout ao chamar o serviço de IA.")
            return Response(
                {"error": "Serviço de IA indisponível (timeout)."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error("Erro 401 Unauthorized ao chamar a API da IA. Verifique a API Key.")
                return Response(
                    {"error": "Serviço de IA não autorizado. Configuração inválida."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
            else:
                logger.error(f"HTTPError ao chamar a API da IA: {e}")
                return Response(
                    {"error": "Erro no serviço de IA."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
        except ValueError as e:
            logger.warning(f"Dados de entrada inválidos para geração de quiz: {e}")
            return Response(
                {"error": f"Dados inválidos: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Erro interno ao gerar quiz: {e}", exc_info=True)
            return Response(
                {"error": "Erro inesperado no servidor."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class SubmitAttemptAPIView(generics.GenericAPIView):
    """
    Endpoint para um usuário submeter as respostas de uma tentativa de quiz.
    URL: POST /api/assessment/submit-attempt/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = AttemptSubmissionSerializer

    def post(self, request, *args, **kwargs):
        # 1. Validar dados de entrada
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # 2. Extrair dados validados
        quiz_id = serializer.validated_data['quiz_id']
        user_answers = serializer.validated_data['answers']
        user = request.user

        # 3. Verificar se o quiz existe e o usuário tem acesso
        try:
            quiz = Quiz.objects.get(
                id=quiz_id,
                topic__course__user=user
            )
        except Quiz.DoesNotExist:
            return Response(
                {'error': 'Quiz não encontrado ou não pertence ao usuário.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4. Validar se há respostas
        if not user_answers:
            return Response(
                {'error': 'É necessário fornecer pelo menos uma resposta.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. Pega todas as perguntas do quiz de uma vez para evitar múltiplas queries
        questions = {q.id: q for q in quiz.questions.all()}
        
        correct_count = 0
        answers_to_create = []

        try:
            with transaction.atomic():
                # 6. Cria o objeto da Tentativa (Attempt)
                attempt = Attempt.objects.create(user=user, quiz=quiz)

                for answer_data in user_answers:
                    question_id = answer_data['question_id']
                    question = questions.get(question_id)

                    if not question: 
                        continue  # Ignora respostas para perguntas que não são deste quiz

                    is_correct = (
                        str(answer_data['user_answer']).upper() == 
                        str(question.correct_answer).upper()
                    )
                    if is_correct:
                        correct_count += 1
                    
                    answers_to_create.append(
                        Answer(
                            attempt=attempt,
                            question=question,
                            user_answer=answer_data['user_answer'],
                            is_correct=is_correct
                        )
                    )
                
                # 7. Salva todas as respostas de uma vez
                Answer.objects.bulk_create(answers_to_create)

                # 8. Atualiza a pontuação da tentativa
                total_questions = len(questions)
                attempt.correct_answers_count = correct_count
                attempt.incorrect_answers_count = total_questions - correct_count
                attempt.score = (correct_count / total_questions) * 100 if total_questions > 0 else 0
                attempt.save()

            # 9. Retorna a tentativa criada
            response_serializer = AttemptDetailSerializer(attempt)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"error": f"Erro ao processar tentativa: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class QuizViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API para listar e ver detalhes dos Quizzes disponíveis.
    - GET /api/assessment/quizzes/
    - GET /api/assessment/quizzes/{id}/
    """
    queryset = Quiz.objects.all()
    serializer_class = QuizDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtra para mostrar apenas quizzes de tópicos do usuário."""
        return self.queryset.filter(
            topic__course__user=self.request.user
        ).select_related('topic').prefetch_related('questions')


class AttemptViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API para listar e ver detalhes das Tentativas de um usuário.
    - GET /api/assessment/attempts/
    - GET /api/assessment/attempts/{id}/
    """
    queryset = Attempt.objects.all()
    serializer_class = AttemptDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtra para mostrar apenas as tentativas do usuário logado."""
        return self.queryset.filter(
            user=self.request.user
        ).select_related('quiz').prefetch_related('answers__question')