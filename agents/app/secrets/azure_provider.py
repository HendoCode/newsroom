"""The ``azure`` backend — Azure Key Vault via ``DefaultAzureCredential`` (managed identity in
production; the developer's ``az login``/env-based credential elsewhere) — no credential is ever
stored here, only the vault URL.

Key Vault secret names may only contain alphanumerics and hyphens (no underscores), so a name
like ``ANTHROPIC_API_KEY`` is normalized to ``ANTHROPIC-API-KEY`` before the lookup.

``azure-identity``/``azure-keyvault-secrets`` are imported lazily inside
:meth:`_client_or_create`, guarded like ``app/render/pdf.py``'s Playwright import, so an
``env``-backend deployment never needs the Azure SDK installed to boot.
"""

from __future__ import annotations

from typing import Any

from .provider import CachingSecretsProvider, SecretNotFoundError


class AzureSecretsProvider(CachingSecretsProvider):
    def __init__(
        self,
        *,
        vault_url: str,
        ttl_seconds: float = 300.0,
        client: Any | None = None,
    ) -> None:
        """``client``, when passed, is used as-is (the test seam — a fake/mocked
        ``SecretClient``) and the Azure SDK is never imported. Production leaves it unset; the
        real client is built lazily on first fetch."""
        super().__init__(ttl_seconds=ttl_seconds)
        self._vault_url = vault_url
        self._client = client

    def _client_or_create(self) -> Any:
        if self._client is None:
            if not self._vault_url:
                raise RuntimeError(
                    "SECRETS_AZURE_VAULT_URL is not configured — required for "
                    "SECRETS_BACKEND=azure"
                )
            try:
                from azure.identity import DefaultAzureCredential
                from azure.keyvault.secrets import SecretClient
            except ImportError as exc:
                raise RuntimeError(
                    "azure-identity/azure-keyvault-secrets are not installed — required for "
                    "SECRETS_BACKEND=azure"
                ) from exc
            self._client = SecretClient(
                vault_url=self._vault_url, credential=DefaultAzureCredential()
            )
        return self._client

    @staticmethod
    def _normalize(name: str) -> str:
        return name.replace("_", "-")

    def _fetch(self, name: str) -> str:
        client = self._client_or_create()
        from azure.core.exceptions import ResourceNotFoundError

        try:
            secret = client.get_secret(self._normalize(name))
        except ResourceNotFoundError as exc:
            raise SecretNotFoundError(name) from exc
        return secret.value
