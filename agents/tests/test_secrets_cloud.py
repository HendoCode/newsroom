"""aws/azure SecretsProvider backends, with the SDK client mocked via the DI seam
(`client=` on the constructor) — never touches the network or imports the real SDK."""

from __future__ import annotations

import pytest
from azure.core.exceptions import ResourceNotFoundError

from app.secrets import SecretNotFoundError
from app.secrets.aws_provider import AwsSecretsProvider
from app.secrets.azure_provider import AzureSecretsProvider


class FakeSsmClient:
    class exceptions:
        class ParameterNotFound(Exception):
            pass

    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.calls: list[str] = []

    def get_parameter(self, *, Name: str, WithDecryption: bool) -> dict:
        self.calls.append(Name)
        if Name not in self.values:
            raise self.exceptions.ParameterNotFound("not found")
        return {"Parameter": {"Value": self.values[Name]}}


class FakeSecret:
    def __init__(self, value: str) -> None:
        self.value = value


class FakeKeyVaultClient:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.calls: list[str] = []

    def get_secret(self, name: str) -> FakeSecret:
        self.calls.append(name)
        if name not in self.values:
            raise ResourceNotFoundError("not found")
        return FakeSecret(self.values[name])


# --- AWS (SSM Parameter Store) --------------------------------------------------------------


def test_aws_provider_fetches_by_prefixed_name() -> None:
    client = FakeSsmClient({"/content-machine/ANTHROPIC_API_KEY": "aws-secret-value"})
    provider = AwsSecretsProvider(prefix="/content-machine/", client=client)
    assert provider.get("ANTHROPIC_API_KEY") == "aws-secret-value"
    assert client.calls == ["/content-machine/ANTHROPIC_API_KEY"]


def test_aws_provider_raises_secret_not_found() -> None:
    client = FakeSsmClient({})
    provider = AwsSecretsProvider(prefix="/content-machine/", client=client)
    with pytest.raises(SecretNotFoundError):
        provider.get("MISSING")


def test_aws_provider_caches_so_the_client_is_called_once(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeSsmClient({"/content-machine/ANTHROPIC_API_KEY": "aws-secret-value"})
    provider = AwsSecretsProvider(prefix="/content-machine/", client=client, ttl_seconds=300.0)
    provider.get("ANTHROPIC_API_KEY")
    provider.get("ANTHROPIC_API_KEY")
    assert client.calls == ["/content-machine/ANTHROPIC_API_KEY"]


def test_aws_provider_force_refresh_re_reads() -> None:
    values = {"/content-machine/ANTHROPIC_API_KEY": "first-value"}
    client = FakeSsmClient(values)
    provider = AwsSecretsProvider(prefix="/content-machine/", client=client, ttl_seconds=300.0)
    assert provider.get("ANTHROPIC_API_KEY") == "first-value"

    values["/content-machine/ANTHROPIC_API_KEY"] = "rotated-value"
    assert provider.get("ANTHROPIC_API_KEY") == "first-value"
    assert provider.get("ANTHROPIC_API_KEY", force_refresh=True) == "rotated-value"


def test_aws_provider_never_imports_boto3_when_client_is_injected() -> None:
    # No boto3 call happens as long as a client is supplied — the constructor never imports it.
    client = FakeSsmClient({"/content-machine/X": "v"})
    provider = AwsSecretsProvider(client=client)
    assert provider.get("X") == "v"


# --- Azure (Key Vault) -----------------------------------------------------------------------


def test_azure_provider_fetches_and_normalizes_underscores() -> None:
    client = FakeKeyVaultClient({"ANTHROPIC-API-KEY": "azure-secret-value"})
    provider = AzureSecretsProvider(vault_url="https://v.vault.azure.net/", client=client)
    assert provider.get("ANTHROPIC_API_KEY") == "azure-secret-value"
    assert client.calls == ["ANTHROPIC-API-KEY"]


def test_azure_provider_raises_secret_not_found() -> None:
    client = FakeKeyVaultClient({})
    provider = AzureSecretsProvider(vault_url="https://v.vault.azure.net/", client=client)
    with pytest.raises(SecretNotFoundError):
        provider.get("MISSING")


def test_azure_provider_caches_so_the_client_is_called_once() -> None:
    client = FakeKeyVaultClient({"ANTHROPIC-API-KEY": "azure-secret-value"})
    provider = AzureSecretsProvider(
        vault_url="https://v.vault.azure.net/", client=client, ttl_seconds=300.0
    )
    provider.get("ANTHROPIC_API_KEY")
    provider.get("ANTHROPIC_API_KEY")
    assert client.calls == ["ANTHROPIC-API-KEY"]


def test_azure_provider_force_refresh_re_reads() -> None:
    values = {"ANTHROPIC-API-KEY": "first-value"}
    client = FakeKeyVaultClient(values)
    provider = AzureSecretsProvider(
        vault_url="https://v.vault.azure.net/", client=client, ttl_seconds=300.0
    )
    assert provider.get("ANTHROPIC_API_KEY") == "first-value"

    values["ANTHROPIC-API-KEY"] = "rotated-value"
    assert provider.get("ANTHROPIC_API_KEY") == "first-value"
    assert provider.get("ANTHROPIC_API_KEY", force_refresh=True) == "rotated-value"


def test_azure_provider_requires_vault_url_when_no_client_injected() -> None:
    provider = AzureSecretsProvider(vault_url="")
    with pytest.raises(RuntimeError):
        provider.get("ANTHROPIC_API_KEY")
