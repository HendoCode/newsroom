"""Backend selection: turns the ``SECRETS_BACKEND`` config knob into a concrete
:class:`~app.secrets.provider.SecretsProvider`. ``@lru_cache`` gives one provider instance per
distinct config tuple — mirroring ``app.config.get_settings``'s own caching — so its in-memory
secret cache is actually shared across calls within a process; ``reset_secrets_provider`` (test
seam, same shape as ``get_settings.cache_clear``) drops it so a later call rebuilds fresh.
"""

from __future__ import annotations

from functools import lru_cache

from .aws_provider import AwsSecretsProvider
from .azure_provider import AzureSecretsProvider
from .env_provider import EnvSecretsProvider
from .provider import SecretsProvider

_SUPPORTED_BACKENDS = ("env", "aws", "azure")


@lru_cache
def get_secrets_provider(
    *,
    backend: str,
    ttl_seconds: float,
    aws_ssm_prefix: str = "/newsroom/",
    azure_vault_url: str = "",
) -> SecretsProvider:
    normalized = backend.strip().lower()
    if normalized == "env":
        return EnvSecretsProvider(ttl_seconds=ttl_seconds)
    if normalized == "aws":
        return AwsSecretsProvider(prefix=aws_ssm_prefix, ttl_seconds=ttl_seconds)
    if normalized == "azure":
        return AzureSecretsProvider(vault_url=azure_vault_url, ttl_seconds=ttl_seconds)
    raise ValueError(
        f"Unknown SECRETS_BACKEND {backend!r} (expected one of {_SUPPORTED_BACKENDS})"
    )


def reset_secrets_provider() -> None:
    """Test seam: drop every cached provider instance (and its in-memory secret cache) so the
    next :func:`get_secrets_provider` call rebuilds from current config/env."""
    get_secrets_provider.cache_clear()
