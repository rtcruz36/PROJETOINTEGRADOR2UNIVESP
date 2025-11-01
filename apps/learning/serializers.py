# apps/learning/serializers.py

from django.db import transaction
from django.db.models import Max
from rest_framework import serializers

from apps.core.services import deepseek_service
from .models import Course, Topic, Subtopic

import logging

logger = logging.getLogger(__name__)


class SubtopicSerializer(serializers.ModelSerializer):
    """Serializador para o modelo Subtopic."""

    class Meta:
        model = Subtopic
        fields = ['id', 'title', 'details', 'order', 'is_completed']
        read_only_fields = ['id']


class TopicSerializer(serializers.ModelSerializer):
    """Serializador para o modelo Topic, incluindo subtópicos aninhados."""

    subtopics = SubtopicSerializer(many=True, read_only=True)

    class Meta:
        model = Topic
        fields = [
            'id',
            'title',
            'slug',
            'course',
            'suggested_study_plan',
            'order',
            'created_at',
            'subtopics',
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'subtopics']


class TopicWriteSerializer(serializers.ModelSerializer):
    """Serializer para criação/edição manual de tópicos."""

    class Meta:
        model = Topic
        fields = ['id', 'course', 'title', 'suggested_study_plan', 'order']
        read_only_fields = ['id', 'order']

    def validate_course(self, value):
        request = self.context['request']
        if value.user != request.user:
            raise serializers.ValidationError(
                "Não é permitido adicionar tópicos em cursos de outro usuário."
            )
        return value

    def validate(self, attrs):
        course = attrs.get('course') or getattr(self.instance, 'course', None)
        title = attrs.get('title')
        if course and title:
            qs = Topic.objects.filter(course=course, title__iexact=title)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'title': 'Já existe um tópico com este título para o curso informado.'
                })
        return super().validate(attrs)

    def create(self, validated_data):
        course = validated_data['course']
        next_order = (course.topics.aggregate(max_order=Max('order'))['max_order'] or 0) + 1
        validated_data['order'] = next_order
        return super().create(validated_data)


class ReorderSerializer(serializers.Serializer):
    """Serializer utilitário para validar payloads de reordenação."""

    ordered_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
        help_text="Lista ordenada com os IDs na nova ordem."
    )

    def validate_ordered_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("IDs duplicados não são permitidos.")
        return value


class CourseWriteSerializer(serializers.ModelSerializer):
    """Serializer para criação/edição de cursos."""

    class Meta:
        model = Course
        fields = ['id', 'title', 'description']
        read_only_fields = ['id']

    def validate_title(self, value):
        user = self.context['request'].user
        qs = Course.objects.filter(user=user, title__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Você já possui um curso com este título.')
        return value


class CourseCreationSerializer(serializers.Serializer):
    """Serializador específico para o fluxo de criação de Curso + Tópico + Subtópicos."""

    course_title = serializers.CharField(
        max_length=200,
        required=True,
        help_text="Título da disciplina. Ex: Cálculo I"
    )
    topic_title = serializers.CharField(
        max_length=200,
        required=True,
        help_text="Tópico principal a ser estudado. Ex: Limites e Derivadas"
    )
    course_description = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Descrição opcional da disciplina."
    )

    def create(self, validated_data):
        course_title = validated_data["course_title"].strip()
        topic_title = validated_data["topic_title"].strip()
        course_description = (validated_data.get("course_description") or "").strip()
        user = self.context["request"].user

        # 1) Course case-insensitive (get_or_create não aceita __iexact)
        course = (
            Course.objects
            .filter(user=user, title__iexact=course_title)
            .first()
        )
        if not course:
            course = Course.objects.create(
                user=user,
                title=course_title,
                description=course_description
            )

        # 2) Topic case-insensitive
        topic = (
            Topic.objects
            .filter(course=course, title__iexact=topic_title)
            .first()
        )
        topic_created = False
        if not topic:
            next_order = (course.topics.aggregate(max_order=Max('order'))['max_order'] or 0) + 1
            topic = Topic.objects.create(course=course, title=topic_title, order=next_order)
            topic_created = True

        # 3) Popular com IA só quando recém-criado
        if topic_created:
            try:
                # Plano sugerido (string). Se vier fallback vazio, apenas não grava nada.
                plan_text = deepseek_service.sugerir_plano_de_topico(course.title, topic.title)
                if plan_text:
                    topic.suggested_study_plan = plan_text
                    topic.save(update_fields=["suggested_study_plan"])

                # Subtópicos sugeridos (list[str] ou [])
                suggested_subtopics = deepseek_service.sugerir_subtopicos(topic) or []

                # Normalização: remover vazios, duplicados e espaços
                seen = set()
                cleaned = []
                for s in suggested_subtopics:
                    s_norm = (s or "").strip()
                    if not s_norm:
                        continue
                    if s_norm.lower() in seen:
                        continue
                    seen.add(s_norm.lower())
                    cleaned.append(s_norm)

                # Criação em lote (ordem começando em 1)
                if cleaned:
                    with transaction.atomic():
                        Subtopic.objects.bulk_create([
                            Subtopic(topic=topic, title=title, order=idx)
                            for idx, title in enumerate(cleaned, start=1)
                        ])
                else:
                    logger.warning(
                        "IA não retornou subtópicos válidos para o tópico '%s'.",
                        topic.title
                    )

            except Exception as e:
                # Não quebra o fluxo de criação do curso/tópico
                logger.exception("Falha ao popular tópico com dados da IA: %s", e)

        return topic


class CourseDetailSerializer(serializers.ModelSerializer):
    """Serializador para listar e detalhar Cursos, mostrando os tópicos aninhados."""

    topics = TopicSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'created_at', 'topics']


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = '__all__'
