# apps/assessment/views.py
import logging

import requests
from django.db import transaction
from django.db.models import Avg
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Quiz, Question, Attempt, Answer
from .serializers import (
    QuizDetailSerializer,
    AttemptDetailSerializer,
    QuizGenerationSerializer,
    AttemptSubmissionSerializer,
    QuizWriteSerializer,
    QuestionManageSerializer,
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


def _refresh_total_questions(quiz: Quiz):
    """Atualiza o total de perguntas registrado no quiz."""
    quiz.total_questions = quiz.questions.count()
    quiz.save(update_fields=['total_questions'])


class QuizViewSet(viewsets.ModelViewSet):
    """API para listar, editar, criar e remover quizzes."""

    queryset = Quiz.objects.all()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = self.queryset.filter(
            topic__course__user=self.request.user
        ).select_related('topic').prefetch_related('questions')

        topic_id = self.request.query_params.get('topic')
        if topic_id:
            queryset = queryset.filter(topic_id=topic_id)

        return queryset

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve', 'retry', 'recommended']:
            return QuizDetailSerializer
        return QuizWriteSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def perform_create(self, serializer):
        quiz = serializer.save()
        _refresh_total_questions(quiz)

    def perform_update(self, serializer):
        quiz = serializer.save()
        _refresh_total_questions(quiz)

    def perform_destroy(self, instance):
        instance.delete()

    @action(detail=True, methods=['post'], url_path='retry')
    def retry(self, request, pk=None):
        """Permite refazer um quiz específico."""
        quiz = self.get_object()
        serializer = QuizDetailSerializer(quiz, context={'request': request})

        message = "Quiz pronto para ser refeito."
        last_attempt = quiz.attempts.filter(user=request.user).order_by('-completed_at').first()
        if last_attempt:
            message = "Você já tentou este quiz. Que tal revisar as explicações e tentar novamente?"

        return Response({'quiz': serializer.data, 'message': message})

    @action(detail=False, methods=['get'], url_path='recommended')
    def recommended(self, request):
        """Retorna o próximo quiz recomendado para o usuário."""
        quizzes = self.get_queryset()

        recommended_quiz = quizzes.filter(attempts__isnull=True).order_by('created_at').first()
        recommendation_reason = "Este é um novo quiz que você ainda não respondeu."

        if not recommended_quiz:
            recommended_quiz = (
                quizzes.annotate(avg_score=Avg('attempts__score'))
                .order_by('avg_score', '-created_at')
                .first()
            )
            if recommended_quiz and recommended_quiz.attempts.exists():
                recommendation_reason = (
                    "Recomendamos revisar este quiz para melhorar sua pontuação média."
                )

        if not recommended_quiz:
            return Response(
                {'detail': 'Nenhum quiz disponível no momento.'},
                status=status.HTTP_204_NO_CONTENT
            )

        serializer = QuizDetailSerializer(recommended_quiz, context={'request': request})
        return Response({'quiz': serializer.data, 'message': recommendation_reason})


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


class QuestionViewSet(viewsets.ModelViewSet):
    """Permite criar, editar e remover perguntas manualmente."""

    serializer_class = QuestionManageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Question.objects.filter(
            quiz__topic__course__user=self.request.user
        ).select_related('quiz', 'subtopic', 'quiz__topic')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    def perform_create(self, serializer):
        question = serializer.save()
        _refresh_total_questions(question.quiz)

    def perform_update(self, serializer):
        question = serializer.save()
        _refresh_total_questions(question.quiz)

    def perform_destroy(self, instance):
        quiz = instance.quiz
        instance.delete()
        _refresh_total_questions(quiz)