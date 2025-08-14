# apps/assessment/views.py

from rest_framework import viewsets, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import Quiz, Question, Attempt, Answer
from .serializers import (
    QuizDetailSerializer, 
    AttemptDetailSerializer,
    QuizGenerationSerializer,
    AttemptSubmissionSerializer
)
from apps.core.services import deepseek_service
from apps.learning.models import Topic


class QuizGenerationAPIView(generics.GenericAPIView):
    """
    Endpoint para gerar um novo Quiz sob demanda usando a IA.
    URL: POST /api/assessment/generate-quiz/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = QuizGenerationSerializer

    def post(self, request):
        # 1. Validar dados de entrada
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            # CORREÇÃO: Tratar o erro de validação para manter formato consistente
            errors = serializer.errors
            if 'non_field_errors' in errors:
                # Se for erro de validação customizada, pegar a mensagem
                return Response(
                    {'error': errors['non_field_errors'][0]}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        # 2. Extrair dados validados
        data = serializer.validated_data
        topic_id = data['topic_id']
        num_easy = data['num_easy']
        num_moderate = data['num_moderate']
        num_hard = data['num_hard']

        # 3. Verificar se o tópico existe e pertence ao usuário
        try:
            topic = Topic.objects.get(
                id=topic_id, 
                course__user=request.user
            )
        except Topic.DoesNotExist:
            return Response(
                {'error': 'Tópico não encontrado ou não pertence ao usuário.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # 4. Chamar o serviço da IA para obter o conteúdo do quiz
            quiz_data = deepseek_service.gerar_quiz_completo(
                topico=topic,
                num_faceis=num_easy,
                num_moderadas=num_moderate,
                num_dificeis=num_hard
            )
            
            if not quiz_data:
                return Response(
                    {'error': 'Não foi possível gerar o quiz. Tente novamente.'}, 
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )

            # 5. Salvar o quiz e suas perguntas no banco de dados em uma transação
            with transaction.atomic():
                # Cria o objeto Quiz
                new_quiz = Quiz.objects.create(
                    topic=topic,
                    title=quiz_data.get('quiz_title', f"Quiz sobre {topic.title}"),
                    description=quiz_data.get('quiz_description', ''),
                    total_questions=len(quiz_data.get('questions', []))
                )
                
                # Cria todas as perguntas associadas
                questions_to_create = []
                for q_data in quiz_data.get('questions', []):
                    questions_to_create.append(
                        Question(
                            quiz=new_quiz,
                            question_text=q_data.get('question_text'),
                            choices=q_data.get('choices'),
                            correct_answer=q_data.get('correct_answer'),
                            difficulty=q_data.get('difficulty', 'MODERATE').upper(),
                            explanation=q_data.get('explanation', '')
                        )
                    )
                Question.objects.bulk_create(questions_to_create)

            # 6. Retornar o quiz recém-criado
            response_serializer = QuizDetailSerializer(new_quiz)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response(
                {"error": f"Ocorreu um erro inesperado: {str(e)}"}, 
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

