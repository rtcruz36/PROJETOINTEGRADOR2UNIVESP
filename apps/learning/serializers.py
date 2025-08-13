# apps/learning/serializers.py

from rest_framework import serializers
from .models import Course, Topic, Subtopic
from apps.core.services import deepseek_service

class SubtopicSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Subtopic.
    Reflete os campos do models.py: title, details, order, is_completed.
    """
    class Meta:
        model = Subtopic
        # Campos ajustados para corresponder ao modelo
        fields = ['id', 'title', 'details', 'order', 'is_completed']
        read_only_fields = ['id']

class TopicSerializer(serializers.ModelSerializer):
    """
    Serializador para o modelo Topic, incluindo seus subtópicos aninhados.
    """
    subtopics = SubtopicSerializer(many=True, read_only=True)
    
    class Meta:
        model = Topic
        # Campos ajustados para corresponder ao modelo
        fields = ['id', 'title', 'slug', 'course', 'suggested_study_plan', 'order', 'created_at', 'subtopics']
        read_only_fields = ['id', 'slug', 'created_at', 'subtopics']

class CourseCreationSerializer(serializers.Serializer):
    """
    Serializador específico para o fluxo de criação de Curso + Tópico + Subtópicos.
    Não está atrelado a um modelo, apenas define os campos de entrada da API.
    """
    course_title = serializers.CharField(max_length=200, required=True, help_text="Título da disciplina. Ex: Cálculo I")
    topic_title = serializers.CharField(max_length=200, required=True, help_text="Tópico principal a ser estudado. Ex: Limites e Derivadas")
    course_description = serializers.CharField(required=False, allow_blank=True, help_text="Descrição opcional da disciplina.")

    def create(self, validated_data):
        """
        Lógica central que orquestra a criação dos objetos no banco de dados.
        """
        course_title = validated_data['course_title']
        topic_title = validated_data['topic_title']
        course_description = validated_data.get('course_description', '')
        user = self.context['request'].user

        # 1. Cria ou obtém o Curso (evita duplicatas para o mesmo usuário)
        course, _ = Course.objects.get_or_create(
            user=user,
            title__iexact=course_title,
            defaults={'title': course_title, 'description': course_description}
        )

        # 2. Cria o Tópico principal associado ao curso
        # Usamos get_or_create para evitar erro se o tópico já existir
        topic, topic_created = Topic.objects.get_or_create(
            course=course,
            title__iexact=topic_title,
            defaults={'title': topic_title}
        )

        # 3. Se o tópico foi recém-criado, busca sugestões da IA
        if topic_created:
            # Chama o serviço da IA para gerar o plano de estudo e os subtópicos
            try:
                # Gera o plano de estudo textual para o campo 'suggested_study_plan'
                plan_text = deepseek_service.sugerir_plano_de_topico(course.title, topic.title)
                topic.suggested_study_plan = plan_text
                topic.save()

                # Gera a lista de subtópicos
                suggested_subtopics = deepseek_service.sugerir_subtopicos(topic)

                # Cria os objetos Subtopic no banco de dados
                Subtopic.objects.bulk_create([
                    Subtopic(topic=topic, title=subtopic_title, order=index)
                    for index, subtopic_title in enumerate(suggested_subtopics)
                ])
            except Exception as e:
                # Se a API falhar, o tópico ainda existe, mas sem subtópicos.
                # O ideal é logar esse erro.
                print(f"ERRO: Falha ao popular tópico com dados da IA: {e}")
        
        return topic # Retorna o tópico criado/encontrado

class CourseDetailSerializer(serializers.ModelSerializer):
    """
    Serializador para listar e detalhar Cursos, mostrando os tópicos aninhados.
    """
    topics = TopicSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'created_at', 'topics']

