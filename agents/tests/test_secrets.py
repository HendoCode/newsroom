"""The env backend + factory selection + config wiring (app/secrets/, app/config.py)."""

from __future__ import annotations

import time

import pytest

from app.config import get_settings
from app.secrets import SecretNotFoundError, get_secrets_provider, reset_secrets_provider
from app.secrets.aws_provider import AwsSecretsProvider
from app.secrets.azure_provider import AzureSecretsProvider
from app.secrets.env_provider import EnvSecretsProvider


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "MONGO_URL",
        "BRAIN_REPO_URL",
        "BRAIN_DEPLOY_KEY",
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REFRESH_TOKEN",
        "SECRETS_BACKEND",
        "SECRETS_CACHE_TTL_SECONDS",
        "SECRETS_AWS_SSM_PREFIX",
        "SECRETS_AZURE_VAULT_URL",
        "TEST_SECRET",
    ):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    reset_secrets_provider()
    yield
    get_settings.cache_clear()
    reset_secrets_provider()


# --- EnvSecretsProvider: resolve, cache, force-refresh -----------------------------------------


def test_env_provider_resolves_from_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_SECRET", "first-value")
    provider = EnvSecretsProvider()
    assert provider.get("TEST_SECRET") == "first-value"


def test_env_provider_raises_when_unset() -> None:
    provider = EnvSecretsProvider()
    with pytest.raises(SecretNotFoundError):
        provider.get("TEST_SECRET")


def test_env_provider_caches_until_force_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_SECRET", "first-value")
    provider = EnvSecretsProvider(ttl_seconds=300.0)
    assert provider.get("TEST_SECRET") == "first-value"

    # Rotate the underlying value — a plain get() must still see the cached one.
    monkeypatch.setenv("TEST_SECRET", "rotated-value")
    assert provider.get("TEST_SECRET") == "first-value"

    # force_refresh skips the cache and picks up the rotation with no restart.
    assert provider.get("TEST_SECRET", force_refresh=True) == "rotated-value"
    # ...and the refreshed value is itself now cached.
    monkeypatch.setenv("TEST_SECRET", "third-value")
    assert provider.get("TEST_SECRET") == "rotated-value"


def test_env_provider_ttl_expiry_re_reads_without_force_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_SECRET", "first-value")
    provider = EnvSecretsProvider(ttl_seconds=0.05)
    assert provider.get("TEST_SECRET") == "first-value"

    monkeypatch.setenv("TEST_SECRET", "rotated-value")
    time.sleep(0.1)
    assert provider.get("TEST_SECRET") == "rotated-value"


def test_env_provider_invalidate_then_get_re_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_SECRET", "first-value")
    provider = EnvSecretsProvider(ttl_seconds=300.0)
    assert provider.get("TEST_SECRET") == "first-value"

    monkeypatch.setenv("TEST_SECRET", "rotated-value")
    provider.invalidate("TEST_SECRET")
    assert provider.get("TEST_SECRET") == "rotated-value"


def test_env_provider_invalidate_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_SECRET", "first-value")
    provider = EnvSecretsProvider(ttl_seconds=300.0)
    provider.get("TEST_SECRET")

    monkeypatch.setenv("TEST_SECRET", "rotated-value")
    provider.invalidate()
    assert provider.get("TEST_SECRET") == "rotated-value"


# --- Factory: backend selection ------------------------------------------------------------


def test_factory_selects_env_by_default() -> None:
    provider = get_secrets_provider(backend="env", ttl_seconds=300.0)
    assert isinstance(provider, EnvSecretsProvider)


def test_factory_selects_aws() -> None:
    provider = get_secrets_provider(backend="aws", ttl_seconds=300.0, aws_ssm_prefix="/x/")
    assert isinstance(provider, AwsSecretsProvider)


def test_factory_selects_azure() -> None:
    provider = get_secrets_provider(
        backend="azure", ttl_seconds=300.0, azure_vault_url="https://v.vault.azure.net/"
    )
    assert isinstance(provider, AzureSecretsProvider)


def test_factory_is_case_insensitive() -> None:
    provider = get_secrets_provider(backend="ENV", ttl_seconds=300.0)
    assert isinstance(provider, EnvSecretsProvider)


def test_factory_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError):
        get_secrets_provider(backend="gcp", ttl_seconds=300.0)


def test_factory_caches_the_same_instance_for_the_same_config() -> None:
    a = get_secrets_provider(backend="env", ttl_seconds=300.0)
    b = get_secrets_provider(backend="env", ttl_seconds=300.0)
    assert a is b


def test_reset_secrets_provider_drops_the_cached_instance() -> None:
    a = get_secrets_provider(backend="env", ttl_seconds=300.0)
    reset_secrets_provider()
    b = get_secrets_provider(backend="env", ttl_seconds=300.0)
    assert a is not b


# --- Settings wiring: default env backend, unchanged local-dev behavior --------------------


def test_settings_default_backend_is_env() -> None:
    assert get_settings().secrets_backend == "env"


def test_settings_anthropic_api_key_resolves_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    get_settings.cache_clear()
    reset_secrets_provider()
    assert get_settings().anthropic_api_key == "test-anthropic-key"


def test_settings_anthropic_api_key_defaults_to_empty_string() -> None:
    assert get_settings().anthropic_api_key == ""


def test_settings_mongo_url_resolves_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGO_URL", "mongodb://test/db")
    get_settings.cache_clear()
    reset_secrets_provider()
    assert get_settings().mongo_url == "mongodb://test/db"


def test_settings_brain_git_credentials_resolve_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRAIN_REPO_URL", "git@example.com:brain.git")
    monkeypatch.setenv("BRAIN_DEPLOY_KEY", "test-deploy-key")
    get_settings.cache_clear()
    reset_secrets_provider()
    settings = get_settings()
    assert settings.brain_repo_url == "git@example.com:brain.git"
    assert settings.brain_deploy_key == "test-deploy-key"


def test_settings_brain_git_credentials_default_to_empty_string() -> None:
    settings = get_settings()
    assert settings.brain_repo_url == ""
    assert settings.brain_deploy_key == ""


def test_settings_google_oauth_credentials_resolve_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_REFRESH_TOKEN", "test-refresh-token")
    get_settings.cache_clear()
    reset_secrets_provider()
    settings = get_settings()
    assert settings.google_oauth_client_id == "test-client-id"
    assert settings.google_oauth_client_secret == "test-client-secret"
    assert settings.google_oauth_refresh_token == "test-refresh-token"


def test_settings_google_oauth_credentials_default_to_empty_string() -> None:
    settings = get_settings()
    assert settings.google_oauth_client_id == ""
    assert settings.google_oauth_client_secret == ""
    assert settings.google_oauth_refresh_token == ""


def test_settings_google_oauth_client_id_resolves_via_aws_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end proof of the chosen route (route (b) in the AWS OAuth wiring PR): once
    GOOGLE_OAUTH_CLIENT_ID exists in SSM, a plain property read reaches it live through the same
    shim path brain_repo_url/brain_deploy_key already use — no container env var, no redeploy.
    The real boto3 SSM client is never constructed; a fake stands in for it (same seam
    test_secrets_cloud.py uses)."""

    class FakeSsmClient:
        class exceptions:
            class ParameterNotFound(Exception):
                pass

        def __init__(self, values: dict[str, str]) -> None:
            self.values = values

        def get_parameter(self, *, Name: str, WithDecryption: bool) -> dict:
            if Name not in self.values:
                raise self.exceptions.ParameterNotFound("not found")
            return {"Parameter": {"Value": self.values[Name]}}

    fake_client = FakeSsmClient({"/content-machine/GOOGLE_OAUTH_CLIENT_ID": "real-client-id"})
    monkeypatch.setattr(
        "app.config.get_secrets_provider",
        lambda **_: AwsSecretsProvider(prefix="/content-machine/", client=fake_client),
    )
    monkeypatch.setenv("SECRETS_BACKEND", "aws")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.google_oauth_client_id == "real-client-id"
    # Unpopulated names on the same live backend still degrade to "" (never crash) — the exact
    # clean "not configured" behavior app/review/routes.py's 503 check depends on.
    assert settings.google_oauth_client_secret == ""


def test_has_llm_credentials_and_has_mongo_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default backend is bedrock, but has_llm_credentials now reflects a real key, not the
    # backend name, so it is False out of the box.
    assert get_settings().has_llm_credentials() is False
    assert get_settings().has_mongo() is False

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("MONGO_URL", "mongodb://test/db")
    get_settings.cache_clear()
    reset_secrets_provider()
    assert get_settings().has_llm_credentials() is True
    assert get_settings().has_mongo() is True
