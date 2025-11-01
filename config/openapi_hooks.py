"""Funções auxiliares para customização do schema OpenAPI via drf-spectacular."""
from __future__ import annotations

from typing import Any, Dict

JWT_HIGHLIGHT_TAG = 'Autenticação JWT'
JWT_PATHS = (
    '/api/accounts/auth/jwt/refresh/',
    '/api/accounts/auth/jwt/verify/',
)


def add_jwt_highlight_to_schema(result: Dict[str, Any], generator: Any, request: Any | None, public: bool) -> Dict[str, Any]:
    """Garante que os endpoints de refresh/verify JWT possuam uma tag dedicada."""
    paths = result.get('paths', {})
    for target in JWT_PATHS:
        path_item = paths.get(target, {})
        if not isinstance(path_item, dict):
            continue

        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue

            tags = operation.setdefault('tags', [])
            if JWT_HIGHLIGHT_TAG not in tags:
                tags.append(JWT_HIGHLIGHT_TAG)

    return result
