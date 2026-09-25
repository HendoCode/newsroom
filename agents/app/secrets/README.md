# Secrets shim (provider-agnostic, just-in-time)

A thin `SecretsProvider` seam (`get(name) -> value`) so every secret read in `agents/` resolves
by name from whatever backend is configured — no cloud lock-in, no distributed copies of the
secret, and no code change to switch backends. **A resolver, not a framework**: no control-plane,
no rotation scheduler, no policy engine.

## Backends

Selected by `SECRETS_BACKEND` (`env` default | `aws` | `azure`):

| Backend | Module | Reads from | Credentials |
|---|---|---|---|
| `env` | `env_provider.py` | `os.environ` (process env / a local `.env` sourced into it) | none — dev default, zero cloud deps |
| `aws` | `aws_provider.py` | SSM Parameter Store, `f"{SECRETS_AWS_SSM_PREFIX}{name}"` | ambient IAM (instance/task role in prod, SSO/OIDC elsewhere) via boto3's default credential chain — no AWS key ever stored |
| `azure` | `azure_provider.py` | Key Vault at `SECRETS_AZURE_VAULT_URL`, secret name with `_` → `-` (Key Vault forbids underscores) | `DefaultAzureCredential` (managed identity in prod, `az login` elsewhere) |

Config knobs (all optional; unset = dev default):

- `SECRETS_BACKEND` — `env` (default) | `aws` | `azure`.
- `SECRETS_CACHE_TTL_SECONDS` — how long a resolved value is cached before the next `.get()`
  re-reads the backend (default `300`).
- `SECRETS_AWS_SSM_PREFIX` — SSM parameter path prefix (default `/content-machine/`).
- `SECRETS_AZURE_VAULT_URL` — e.g. `https://<vault-name>.vault.azure.net/`.

These four names are shared verbatim with `web/`'s Node resolver (`web/lib/secrets/`) so both
runtimes behave identically under the same deployment config.

## Just-in-time + force-refresh

`SecretsProvider.get(name)` resolves on first access and caches for `SECRETS_CACHE_TTL_SECONDS`;
`get(name, force_refresh=True)` (or `invalidate(name)` then a plain `get`) skips the cache and
re-reads the backend — the path a rotated secret takes to reach a running process with no
rebuild/restart. `get_secrets_provider(...)` is `@lru_cache`d per config tuple (mirrors
`app.config.get_settings`); `reset_secrets_provider()` is the test seam that drops it.

## What's wired through it

`app/config.py`'s `Settings.anthropic_api_key` / `.mongo_url` / `.brain_repo_url` /
`.brain_deploy_key` are properties that call `get_secrets_provider(...).get(NAME)` (falling
back to `""` on `SecretNotFoundError`, matching the pre-shim empty-string defaults) instead of
being plain pydantic-settings fields. Every other config value (service identity, Mongo db name,
lake/embedding backend, brain root path, etc.) is unaffected — those aren't secrets.
`brain_repo_url`/`brain_deploy_key` back the `cmw-brain-split` ticket's brain-as-clone bootstrap
(`app.git.ensure_brain_available`) — `brain_deploy_key` resolves `BRAIN_DEPLOY_KEY`, an SSH
deploy-key private key (repo-scoped, read-write — see `app/git/ssh_auth.py`), which replaced an
earlier classic-PAT/HTTPS credential (`BRAIN_GIT_TOKEN`) for least-privilege machine push access.

## Testing

`aws`/`azure` providers accept an optional `client=` constructor kwarg — pass a fake/mocked SDK
client and the real `boto3`/`azure-identity` import never happens, so tests never touch the
network (see `tests/test_secrets_cloud.py`). Both SDKs are otherwise imported lazily inside
`_client_or_create`, guarded like `app/render/pdf.py`'s Playwright import, so an `env`-backend
deployment (the default) never needs them installed to boot.
