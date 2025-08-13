# apps/learning/models.py

from django.db import models
from django.conf import settings
from django.utils.text import slugify
from django.urls import reverse

class Course(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='courses',
        verbose_name="Usuário"
    )
    title = models.CharField(
        max_length=200,
        verbose_name="Título da Disciplina"
    )
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name="Descrição"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Data de Criação"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Última Atualização"
    )

    class Meta:
        unique_together = ('user', 'title')
        ordering = ['title']
        verbose_name = "Disciplina"
        verbose_name_plural = "Disciplinas"

    def __str__(self):
        return self.title

class Topic(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='topics',
        verbose_name="Disciplina"
    )
    title = models.CharField(
        max_length=200,
        verbose_name="Título do Tópico"
    )
    slug = models.SlugField(
        max_length=220,
        unique=True,
        blank=True,
        help_text="Identificador único para a URL, gerado a partir do título."
    )
    suggested_study_plan = models.TextField(
        blank=True,
        null=True,
        verbose_name="Plano de Estudo Sugerido"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordem"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('course', 'title')
        ordering = ['order', 'title']
        verbose_name = "Tópico"
        verbose_name_plural = "Tópicos"

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(f"{self.course.user.id}-{self.course.title}-{self.title}")
            self.slug = base_slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        # Este 'topic-detail' precisará de uma URL com esse nome no futuro.
        # Por enquanto, não causa problemas.
        return reverse('topic-detail', kwargs={'slug': self.slug})


class Subtopic(models.Model):
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name='subtopics',
        verbose_name="Tópico"
    )
    title = models.CharField(
        max_length=200,
        verbose_name="Título do Subtópico"
    )
    details = models.TextField(
        blank=True,
        null=True,
        verbose_name="Detalhes"
    )
    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Ordem"
    )
    is_completed = models.BooleanField(
        default=False,
        verbose_name="Concluído"
    )

    class Meta:
        ordering = ['order', 'title']
        verbose_name = "Subtópico"
        verbose_name_plural = "Subtópicos"

    def __str__(self):
        return self.title
