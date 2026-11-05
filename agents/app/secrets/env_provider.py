"""The ``env`` backend — process environment / a local ``.env`` sourced into it. Zero cloud
deps; this is what an unset/``env`` ``SECRETS_BACKEND`` resolves to, so local dev and tests are
unaffected by this shim's existence.
"""

from __future__ import annotations

import os

from .provider import CachingSecretsProvider, SecretNotFoundError


class EnvSecretsProvider(CachingSecretsProvider):
    def _fetch(self, name: str) -> str:
        value = os.environ.get(name)
        if value is None:
            raise SecretNotFoundError(name)
        return value
