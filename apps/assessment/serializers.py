# apps/assessment/serializers.py

from rest_framework import serializers
from .models import Quiz, Question, Attempt, Answer
from apps.learning.models import Topic

# --- Serializadores para Apresentação de Dados (Leitura) ---
class QuestionSerializer(serializers.ModelSerializer):
    """Serializador para exibir uma Pergunta (sem a resposta correta)."""
    class Meta:
        model = Question
        # Excluímos 'correct_answer' e 'explanation' para não entregar a resposta ao usuário antes da hora.
        fields = ['id', 'question_text', 'choices', 'difficulty']


class QuestionManageSerializer(serializers.ModelSerializer):
    """Serializador utilizado para criação e edição de perguntas manualmente."""

    class Meta:
        model = Question
        fields = [
            'id',
            'quiz',
            'subtopic',
            'question_text',
            'choices',
            'correct_answer',
            'difficulty',
            'explanation',
        ]

    def validate_quiz(self, value):
        request = self.context.get('request')
        if request and value.topic.course.user != request.user:
            raise serializers.ValidationError("Você não tem permissão para alterar este quiz.")
        return value

    def validate_subtopic(self, value):
        if not value:
            return value
        request = self.context.get('request')
        if request and value.topic.course.user != request.user:
            raise serializers.ValidationError("Você não tem permissão para usar este subtópico.")
        return value

    def validate(self, attrs):
        choices = attrs.get('choices', getattr(self.instance, 'choices', None))
        correct_answer = attrs.get('correct_answer', getattr(self.instance, 'correct_answer', None))
        quiz = attrs.get('quiz', getattr(self.instance, 'quiz', None))
        subtopic = attrs.get('subtopic', getattr(self.instance, 'subtopic', None))

        if choices is None or not isinstance(choices, dict):
            raise serializers.ValidationError({
                'choices': 'As opções de resposta devem ser um objeto JSON com as chaves das alternativas.'
            })

        if correct_answer and correct_answer not in choices:
            raise serializers.ValidationError({
                'correct_answer': 'A resposta correta precisa corresponder a uma das chaves em "choices".'
            })

        if quiz and subtopic and subtopic.topic_id != quiz.topic_id:
            raise serializers.ValidationError({
                'subtopic': 'O subtópico selecionado precisa pertencer ao mesmo tópico do quiz.'
            })

        return super().validate(attrs)

class AnswerDetailSerializer(serializers.ModelSerializer):
    """Serializador para mostrar os detalhes de uma resposta dada pelo usuário."""
    question = QuestionSerializer(read_only=True)
    explanation = serializers.CharField(source='question.explanation', read_only=True)
    correct_answer = serializers.CharField(source='question.correct_answer', read_only=True)

    class Meta:
        model = Answer
        fields = ['question', 'user_answer', 'is_correct', 'explanation', 'correct_answer']

class AttemptDetailSerializer(serializers.ModelSerializer):
    """Serializador para mostrar o resultado detalhado de uma tentativa."""
    answers = AnswerDetailSerializer(many=True, read_only=True)
    quiz_title = serializers.CharField(source='quiz.title', read_only=True)

    class Meta:
        model = Attempt
        fields = [
            'id', 
            'quiz',
            'quiz_title',
            'score', 
            'correct_answers_count', 
            'incorrect_answers_count', 
            'completed_at', 
            'answers'
        ]

class QuizDetailSerializer(serializers.ModelSerializer):
    """Serializador para exibir um Quiz com todas as suas perguntas."""
    questions = QuestionSerializer(many=True, read_only=True)
    topic_title = serializers.CharField(source='topic.title', read_only=True)

    class Meta:
        model = Quiz
        fields = ['id', 'topic', 'topic_title', 'title', 'description', 'total_questions', 'created_at', 'questions']

# --- Serializadores para Entrada de Dados (Escrita) ---

class QuizWriteSerializer(serializers.ModelSerializer):
    """Serializador utilizado para criação e edição manual de quizzes."""

    class Meta:
        model = Quiz
        fields = ['id', 'topic', 'title', 'description']

    def validate_topic(self, value):
        request = self.context.get('request')
        if request and value.course.user != request.user:
            raise serializers.ValidationError("Você não tem permissão para utilizar este tópico.")
        return value

    def update(self, instance, validated_data):
        topic = validated_data.get('topic')
        if topic and topic != instance.topic:
            request = self.context.get('request')
            if request and topic.course.user != request.user:
                raise serializers.ValidationError("Você não tem permissão para utilizar este tópico.")
        return super().update(instance, validated_data)

class QuizGenerationSerializer(serializers.Serializer):
    """
    Valida a entrada para a geração de um novo quiz. Não está ligado a um modelo.
    """
    topic_id = serializers.IntegerField(
        required=True, 
        help_text="O ID do Tópico para o qual o quiz será gerado."
    )
    num_easy = serializers.IntegerField(default=7, min_value=0)
    num_moderate = serializers.IntegerField(default=7, min_value=0)
    num_hard = serializers.IntegerField(default=6, min_value=0)

    def validate_topic_id(self, value):
        """Verifica se o Topic existe e pertence ao usuário."""
        try:
            user = self.context['request'].user
            topic = Topic.objects.get(id=value, course__user=user)
            return topic  # Retorna o objeto Topic, não o ID
        except Topic.DoesNotExist:
            raise serializers.ValidationError("Tópico não encontrado ou não pertence a você.")

    def validate(self, data):
        """Validação customizada para garantir pelo menos uma pergunta."""
        total_questions = data['num_easy'] + data['num_moderate'] + data['num_hard']
        if total_questions == 0:
            raise serializers.ValidationError({
                'error': 'Deve haver pelo menos uma pergunta no quiz.'
            })
        return data

class SubmitAnswerSerializer(serializers.Serializer):
    """Valida uma única resposta enviada pelo usuário."""
    question_id = serializers.IntegerField()
    user_answer = serializers.CharField(max_length=10)

class AttemptSubmissionSerializer(serializers.Serializer):
    """
    Valida a submissão de uma tentativa de quiz completa.
    """
    quiz_id = serializers.IntegerField()
    answers = SubmitAnswerSerializer(many=True, required=True)

    def validate_quiz_id(self, value):
        """Verifica se o Quiz existe e retorna o ID (não o objeto)."""
        try:
            Quiz.objects.get(id=value)
            return value  # Retorna o ID, não o objeto
        except Quiz.DoesNotExist:
            raise serializers.ValidationError("Quiz não encontrado.")

    def validate_answers(self, value):
        """Verifica se a lista de respostas não está vazia."""
        if not value:
            raise serializers.ValidationError("A lista de respostas não pode estar vazia.")
        return value