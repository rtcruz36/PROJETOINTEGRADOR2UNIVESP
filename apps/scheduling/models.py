# Create your models here.
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from apps.learning.models import Course, Topic # Importamos os modelos do app learning

class StudyPlan(models.Model):
    """
    Representa a META de estudo semanal de um usuário para uma disciplina.
    Ex: Estudar 'Cálculo I' por 60 minutos toda Segunda-Feira.
    """
    # Constantes para os dias da semana, facilitando o uso no código e no admin.
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, 'Segunda-feira'
        TUESDAY = 1, 'Terça-feira'
        WEDNESDAY = 2, 'Quarta-feira'
        THURSDAY = 3, 'Quinta-feira'
        FRIDAY = 4, 'Sexta-feira'
        SATURDAY = 5, 'Sábado'
        SUNDAY = 6, 'Domingo'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='study_plans',
        verbose_name="Usuário"
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='study_plans',
        verbose_name="Disciplina"
    )
    day_of_week = models.IntegerField(
        choices=DayOfWeek.choices,
        verbose_name="Dia da Semana"
    )
    minutes_planned = models.PositiveIntegerField(
        verbose_name="Minutos Planejados",
        validators=[MinValueValidator(1)],
        help_text="Quantos minutos você planeja estudar esta disciplina neste dia."
    )

    class Meta:
        # Garante que o usuário só pode ter um plano por disciplina por dia da semana.
        unique_together = ('user', 'course', 'day_of_week')
        ordering = ['user', 'day_of_week', 'course']
        verbose_name = "Plano de Estudo Semanal"
        verbose_name_plural = "Planos de Estudo Semanais"

    def __str__(self):
        # Ex: "Plano de joao: Cálculo I - Segunda-feira (60 min)"
        return (f"Plano de {self.user.username}: {self.course.title} - "
                f"{self.get_day_of_week_display()} ({self.minutes_planned} min)")


class StudyLog(models.Model):
    """
    Registra uma SESSÃO DE ESTUDO que efetivamente aconteceu.
    Pode ser chamado de "TimeBox" ou "StudySession" também.
    Ex: Usuário estudou o tópico 'Derivadas' por 45 minutos no dia 12/08/2025.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='study_logs',
        verbose_name="Usuário"
    )
    # Opcionalmente, podemos ligar o log a um tópico específico, o que é ótimo para analytics.
    topic = models.ForeignKey(
        Topic,
        on_delete=models.SET_NULL, # Se o tópico for deletado, não perdemos o log de estudo.
        null=True,
        blank=True, # O usuário pode registrar um estudo genérico na disciplina.
        related_name='study_logs',
        verbose_name="Tópico Estudado"
    )
    # Mesmo que o log esteja ligado a um tópico, ter a disciplina facilita as consultas.
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE, # Se a disciplina for deletada, os logs dela não fazem mais sentido.
        related_name='study_logs',
        verbose_name="Disciplina"
    )
    date = models.DateField(
        verbose_name="Data do Estudo"
    )
    minutes_studied = models.PositiveIntegerField(
        verbose_name="Minutos Estudados",
        validators=[MinValueValidator(1)]
    )
    notes = models.TextField(
        blank=True,
        null=True,
        verbose_name="Anotações",
        help_text="O que você aprendeu? Quais foram suas dificuldades?"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at'] # Mostra os logs mais recentes primeiro.
        verbose_name = "Registro de Estudo"
        verbose_name_plural = "Registros de Estudo"

    def __str__(self):
        # Ex: "joao estudou Cálculo I por 45 min em 2025-08-12"
        topic_title = f" ({self.topic.title})" if self.topic else ""
        return (f"{self.user.username} estudou {self.course.title}{topic_title} "
                f"por {self.minutes_studied} min em {self.date}")