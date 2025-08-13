# apps/accounts/views.py

from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import RetrieveUpdateAPIView
from .models import Profile
from .serializers import ProfileSerializer

class UserProfileAPIView(RetrieveUpdateAPIView):
    """
    Endpoint para um usuário ver e atualizar seu próprio perfil.
    - GET: /api/accounts/profile/ (Retorna o perfil do usuário logado)
    - PUT/PATCH: /api/accounts/profile/ (Atualiza o perfil do usuário logado)
    """
    queryset = Profile.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        """
        Sobrescreve o método padrão para sempre retornar o perfil
        do usuário que está fazendo a requisição.
        """
        # Como temos um OneToOneField, podemos acessar o perfil diretamente do usuário.
        return self.request.user.profile
