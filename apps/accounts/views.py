"""Views para o app de contas."""

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserProfileSerializer


class UserProfileAPIView(APIView):
    """Endpoint para um usuário ver e atualizar seu próprio perfil."""

    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser, JSONParser)

    def get(self, request, *args, **kwargs):
        serializer = UserProfileSerializer(request.user, context={"request": request})
        return Response(serializer.data)

    def put(self, request, *args, **kwargs):
        return self._update(request, partial=False)

    def patch(self, request, *args, **kwargs):
        return self._update(request, partial=True)

    def _update(self, request, partial):
        normalized = self._normalize_payload(request)
        serializer = UserProfileSerializer(
            request.user,
            data=normalized,
            partial=partial,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def _normalize_payload(self, request):
        data = {}
        profile_data = {}
        preferences_data = {}

        for key in request.data:
            value = request.data.get(key)
            if key.startswith("profile."):
                field = key.split(".", 1)[1]
                if field == "profile_picture" and value in ("", None):
                    profile_data[field] = None
                else:
                    profile_data[field] = value
            elif key.startswith("preferences."):
                preferences_data[key.split(".", 1)[1]] = value
            else:
                data[key] = value

        if profile_data:
            data["profile"] = profile_data
        if preferences_data:
            data["preferences"] = preferences_data

        return data
