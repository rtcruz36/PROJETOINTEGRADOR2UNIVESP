# apps/assessment/models.py

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
# Importe os modelos do app learning com o caminho completo
from apps.learning.models import Topic, Subtopic

class Quiz(models.Model):
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name='quizzes',
        verbose_name="Tópico"
    )
    title = models.CharField(
        max_length=255,
        verbose_name="Título do Quiz"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Descrição"
    )
    total_questions = models.PositiveIntegerField(
        default=20,
        verbose_name="Número Total de Perguntas"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Data de Criação"
    )

    class Meta:
        app_label = 'apps.assessment'
        ordering = ['-created_at']
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"

    def __str__(self):
        return f"Quiz sobre '{self.topic.title}': {self.title}"


class Question(models.Model):
    class DifficultyLevel(models.TextChoices):
        EASY = 'EASY', 'Fácil'
        MODERATE = 'MODERATE', 'Moderada'
        HARD = 'HARD', 'Difícil'

    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='questions',
        verbose_name="Quiz"
    )
    subtopic = models.ForeignKey(
        Subtopic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='questions',
        verbose_name="Subtópico Específico"
    )
    question_text = models.TextField(
        verbose_name="Texto da Pergunta"
    )
    choices = models.JSONField(
        verbose_name="Opções de Resposta"
    )
    correct_answer = models.CharField(
        max_length=10,
        verbose_name="Resposta Correta"
    )
    difficulty = models.CharField(
        max_length=10,
        choices=DifficultyLevel.choices,
        default=DifficultyLevel.MODERATE,
        verbose_name="Nível de Dificuldade"
    )
    explanation = models.TextField(
        blank=True,
        verbose_name="Justificativa da Resposta"
    )

    class Meta:
        app_label = 'apps.assessment'
        ordering = ['id']
        verbose_name = "Pergunta"
        verbose_name_plural = "Perguntas"

    def __str__(self):
        return f"({self.difficulty}) {self.question_text[:80]}..."


class Attempt(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='attempts',
        verbose_name="Usuário"
    )
    quiz = models.ForeignKey(
        Quiz,
        on_delete=models.CASCADE,
        related_name='attempts',
        verbose_name="Quiz"
    )
    score = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        verbose_name="Pontuação (%)"
    )
    correct_answers_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Respostas Corretas"
    )
    incorrect_answers_count = models.PositiveIntegerField(
        default=0,
        verbose_name="Respostas Incorretas"
    )
    completed_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Data de Conclusão"
    )

    class Meta:
        app_label = 'apps.assessment'
        ordering = ['-completed_at']
        verbose_name = "Tentativa"
        verbose_name_plural = "Tentativas"

    def __str__(self):
        return f"Tentativa de {self.user.username} no quiz '{self.quiz.title}' - {self.score:.2f}%"


class Answer(models.Model):
    attempt = models.ForeignKey(
        Attempt,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name="Tentativa"
    )
    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='answers',
        verbose_name="Pergunta"
    )
    user_answer = models.CharField(
        max_length=10,
        verbose_name="Resposta do Usuário"
    )
    is_correct = models.BooleanField(
        verbose_name="Está Correta?"
    )

    class Meta:
        app_label = 'apps.assessment'
        unique_together = ('attempt', 'question')
        verbose_name = "Resposta do Usuário"
        verbose_name_plural = "Respostas dos Usuários"

    def __str__(self):
        return f"Resposta para Q{self.question.id} na tentativa {self.attempt.id}"
