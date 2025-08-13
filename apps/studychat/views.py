# apps/studychat/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .serializers import StudyChatQuerySerializer
from apps.core.services import deepseek_service

class StudyChatAPIView(APIView):
    """
    Endpoint para o chat de estudo interativo.
    Atua como um proxy para o serviço de IA, adicionando contexto.
    URL: POST /api/chat/ask/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # 1. Validar os dados da requisição usando o serializador
        serializer = StudyChatQuerySerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        pergunta_usuario = validated_data['question']
        historico_conversa = validated_data['history']
        topico_contexto = validated_data.get('topic_id') # Pode ser None ou um objeto Topic

        try:
            # 2. Chamar o serviço do core com os dados validados
            resposta_ia = deepseek_service.responder_pergunta_de_estudo(
                pergunta_usuario=pergunta_usuario,
                historico_conversa=historico_conversa,
                topico_contexto=topico_contexto 
            )

            # 3. Retornar a resposta da IA para o frontend
            response_data = {
                "role": "assistant",
                "content": resposta_ia
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            # Logar o erro `e` seria ideal aqui
            return Response(
                {"error": f"Ocorreu um erro ao processar sua pergunta: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

