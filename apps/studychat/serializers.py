# apps/studychat/serializers.py

from rest_framework import serializers
from apps.learning.models import Topic

class ChatMessageSerializer(serializers.Serializer):
    """
    Valida uma única mensagem no histórico do chat.
    Não está ligado a um modelo.
    """
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()

class StudyChatQuerySerializer(serializers.Serializer):
    """
    Valida a requisição completa para o chat de estudo.
    """
    # A pergunta atual do usuário.
    question = serializers.CharField(max_length=4000, required=True)
    
    # O histórico da conversa, que é uma lista de mensagens.
    # O `allow_empty=True` permite que a primeira pergunta seja enviada com histórico vazio.
    history = ChatMessageSerializer(many=True, required=True, allow_empty=True)
    
    # O ID do tópico é opcional, mas muito útil para dar contexto à IA.
    topic_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_topic_id(self, value):
        """
        Se um topic_id for fornecido, verifica se ele existe e pertence ao usuário.
        """
        if value is None:
            return None
            
        user = self.context['request'].user
        try:
            # Busca o tópico para garantir que ele é válido e acessível pelo usuário.
            topic = Topic.objects.get(id=value, course__user=user)
            return topic # Retorna o objeto Topic completo
        except Topic.DoesNotExist:
            raise serializers.ValidationError("Tópico de contexto não encontrado ou não pertence a você.")
