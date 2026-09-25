"""The ``aws`` backend — AWS Systems Manager Parameter Store, one parameter per secret name
under a shared prefix (default ``/content-machine/``). Ambient IAM credentials only: an
instance/task role in production, the caller's SSO/OIDC session elsewhere — boto3's default
credential chain resolves both, so no AWS key is ever stored here. Secrets Manager would slot in
behind the same ``_fetch`` seam if a future ticket needs it; SSM is the thinner of the two for a
flat name->value lookup and is what this backend implements.

``boto3`` is imported lazily inside :meth:`_client_or_create`, guarded like
``app/render/pdf.py``'s Playwright import, so an ``env``-backend deployment never needs the AWS
SDK installed to boot.
"""

from __future__ import annotations

from typing import Any

from .provider import CachingSecretsProvider, SecretNotFoundError


class AwsSecretsProvider(CachingSecretsProvider):
    def __init__(
        self,
        *,
        prefix: str = "/content-machine/",
        ttl_seconds: float = 300.0,
        client: Any | None = None,
    ) -> None:
        """``client``, when passed, is used as-is (the test seam — a fake/mocked SSM client) and
        boto3 is never imported. Production leaves it unset; the real client is built lazily on
        first fetch."""
        super().__init__(ttl_seconds=ttl_seconds)
        self._prefix = prefix
        self._client = client

    def _client_or_create(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError(
                    "boto3 is not installed — required for SECRETS_BACKEND=aws"
                ) from exc
            self._client = boto3.client("ssm")
        return self._client

    def _fetch(self, name: str) -> str:
        client = self._client_or_create()
        parameter_name = f"{self._prefix}{name}"
        try:
            response = client.get_parameter(Name=parameter_name, WithDecryption=True)
        except client.exceptions.ParameterNotFound as exc:
            raise SecretNotFoundError(name) from exc
        return response["Parameter"]["Value"]
