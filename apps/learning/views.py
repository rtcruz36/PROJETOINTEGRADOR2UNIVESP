# apps/learning/views.py

from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import Course, Topic, Subtopic
from .serializers import (
    CourseCreationSerializer, 
    CourseDetailSerializer, 
    TopicSerializer, 
    SubtopicSerializer
)

class LearningCreationAPIView(generics.CreateAPIView):
    """
    Endpoint único para o fluxo principal de criação.
    Recebe um título de disciplina e um tópico, e cria tudo:
    Curso -> Tópico -> Subtópicos (via IA).
    URL: POST /api/learning/create-study-plan/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CourseCreationSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # O método .create() do serializador faz todo o trabalho pesado
        topic = serializer.save() 
        
        # Retorna o Tópico recém-criado (com subtópicos aninhados) como resposta
        response_serializer = TopicSerializer(topic)
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API para listar e ver detalhes dos Cursos do usuário.
    Não permite criação/edição por aqui para forçar o uso do fluxo principal.
    - GET /api/learning/courses/ (lista todos os cursos)
    - GET /api/learning/courses/{id}/ (detalhes de um curso)
    """
    queryset = Course.objects.all()
    serializer_class = CourseDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtra os cursos para retornar apenas os do usuário logado."""
        return self.queryset.filter(user=self.request.user).prefetch_related('topics__subtopics')


class TopicViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API para listar e ver detalhes dos Tópicos do usuário.
    - GET /api/learning/topics/
    - GET /api/learning/topics/{id}/
    """
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtra os tópicos para retornar apenas os que pertencem ao usuário logado."""
        return self.queryset.filter(course__user=self.request.user).select_related('course').prefetch_related('subtopics')


class SubtopicUpdateAPIView(generics.UpdateAPIView):
    """
    Endpoint específico para atualizar um Subtópico.
    Principalmente para marcar como concluído.
    - PATCH /api/learning/subtopics/{id}/
    """
    queryset = Subtopic.objects.all()
    serializer_class = SubtopicSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Garante que o usuário só pode atualizar seus próprios subtópicos."""
        return self.queryset.filter(topic__course__user=self.request.user)

