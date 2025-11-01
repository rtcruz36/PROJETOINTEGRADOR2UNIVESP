# apps/learning/views.py

from django.db import OperationalError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Course, Topic, Subtopic
from .serializers import (
    CourseCreationSerializer,
    CourseDetailSerializer,
    CourseSerializer,
    CourseWriteSerializer,
    ReorderSerializer,
    SubtopicSerializer,
    SubtopicWriteSerializer,
    TopicSerializer,
    TopicWriteSerializer,
)


class LearningCreationAPIView(generics.CreateAPIView):
    """Endpoint único para o fluxo principal de criação."""

    permission_classes = [IsAuthenticated]
    serializer_class = CourseCreationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        topic = serializer.save()

        response_serializer = TopicSerializer(topic, context={'request': request})
        headers = self.get_success_headers(response_serializer.data)
        return Response(
            response_serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class CourseViewSet(viewsets.ModelViewSet):
    """CRUD completo para os cursos do usuário autenticado."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Course.objects.filter(user=self.request.user)
            .prefetch_related('topics__subtopics')
            .order_by('title')
        )

    def get_serializer_class(self):
        if self.action in {'create', 'update', 'partial_update'}:
            return CourseWriteSerializer
        return CourseDetailSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class TopicViewSet(viewsets.ModelViewSet):
    """Permite gerenciar tópicos de forma independente do fluxo principal."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Topic.objects.filter(course__user=self.request.user)
            .select_related('course')
            .prefetch_related('subtopics')
            .order_by('order', 'title')
        )

    def get_serializer_class(self):
        if self.action in {'create', 'update', 'partial_update'}:
            return TopicWriteSerializer
        return TopicSerializer

    def perform_create(self, serializer):
        serializer.save()


class SubtopicViewSet(viewsets.ModelViewSet):
    """Permite gerenciar subtópicos de forma independente."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Subtopic.objects.filter(topic__course__user=self.request.user)
            .select_related('topic', 'topic__course')
            .order_by('order', 'title')
        )

    def get_serializer_class(self):
        if self.action in {'create', 'update', 'partial_update'}:
            return SubtopicWriteSerializer
        return SubtopicSerializer


class TopicReorderAPIView(generics.GenericAPIView):
    """Atualiza a ordem dos tópicos de um curso."""

    permission_classes = [IsAuthenticated]
    serializer_class = ReorderSerializer

    def post(self, request, course_pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ordered_ids = serializer.validated_data['ordered_ids']

        course = get_object_or_404(Course, pk=course_pk, user=request.user)
        current_ids = list(course.topics.values_list('id', flat=True))

        if set(current_ids) != set(ordered_ids):
            return Response(
                {
                    'detail': 'A lista enviada deve conter todos os tópicos atuais do curso.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            for index, topic_id in enumerate(ordered_ids, start=1):
                Topic.objects.filter(pk=topic_id, course=course).update(order=index)

        updated_topics = (
            Topic.objects.filter(course=course)
            .select_related('course')
            .prefetch_related('subtopics')
            .order_by('order', 'title')
        )
        data = TopicSerializer(updated_topics, many=True, context={'request': request}).data
        return Response(data, status=status.HTTP_200_OK)


class SubtopicReorderAPIView(generics.GenericAPIView):
    """Atualiza a ordem dos subtópicos de um tópico."""

    permission_classes = [IsAuthenticated]
    serializer_class = ReorderSerializer

    def post(self, request, topic_pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ordered_ids = serializer.validated_data['ordered_ids']

        topic = get_object_or_404(Topic, pk=topic_pk, course__user=request.user)
        current_ids = list(topic.subtopics.values_list('id', flat=True))

        if set(current_ids) != set(ordered_ids):
            return Response(
                {
                    'detail': 'A lista enviada deve conter todos os subtópicos atuais do tópico.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            for index, subtopic_id in enumerate(ordered_ids, start=1):
                Subtopic.objects.filter(pk=subtopic_id, topic=topic).update(order=index)

        updated_subtopics = (
            Subtopic.objects.filter(topic=topic)
            .order_by('order', 'title')
        )
        data = SubtopicSerializer(updated_subtopics, many=True, context={'request': request}).data
        return Response(data, status=status.HTTP_200_OK)


class SubtopicUpdateAPIView(generics.UpdateAPIView):
    """Endpoint específico para atualizar um Subtópico."""

    queryset = Subtopic.objects.all()
    serializer_class = SubtopicWriteSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(topic__course__user=self.request.user)


class CourseListView(generics.ListAPIView):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer

    def list(self, request, *args, **kwargs):
        try:
            response = super().list(request, *args, **kwargs)
            return response
        except OperationalError:
            return Response(
                {"error": "Erro ao acessar os dados"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
