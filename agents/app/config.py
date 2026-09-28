"""Service configuration.

Provider keys and other secrets are read from the environment **server-side only** and are
never returned to clients (docs/design.md §6, D14). This is the seam where the LLM module
(Anthropic / OpenAI SDKs) and the MongoDB connection will read their credentials; the walking
skeleton only declares them so the pattern is in place from the first commit.

A subset of these secrets (Anthropic key, Mongo creds, the brain repo URL/SSH deploy key) are
resolved through the just-in-time `app.secrets` shim rather than being plain pydantic-settings
fields — see `app/secrets/README.md`. That lets `SECRETS_BACKEND` swap them to AWS SSM / Azure
Key Vault in production with no code change; left unset (`env`, the default), behavior is
unchanged from a plain env var read.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.secrets import SecretNotFoundError, get_secrets_provider


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    # Service identity / networking.
    service_name: str = "agents"
    environment: str = "development"

    # LLM backend selection (D14 Item 1). "bedrock" uses the BedrockGLMProvider (ambient IAM,
    # zai.glm-5 / zai.glm-4.7 / zai.glm-4.7-flash); "anthropic" keeps the direct Anthropic path;
    # "openai" and "openrouter" both route through the OpenAI-compatible provider
    # (OpenAILLMProvider). "openrouter" is the OpenAI-compatible path pointed at OpenRouter:
    # the same OPENAI_API_KEY slot (an OpenRouter key) with the endpoint defaulting to
    # https://openrouter.ai/api/v1 unless OPENAI_BASE_URL overrides it. Model IDs live here
    # (never literals in tiering.py or provider code) so swapping providers or models is config-only.
    llm_backend: str = "bedrock"
    glm_5_model_id: str = "zai.glm-5"
    glm_4_7_model_id: str = "zai.glm-4.7"
    glm_4_7_flash_model_id: str = "zai.glm-4.7-flash"
    gpt_56_terra_model_id: str = "gpt-5.6-terra"
    # OpenAI-compatible endpoint override for the "openai" and "openrouter" backends. NOT a
    # secret — a plain URL. Blank: "openai" falls back to the openai SDK's own default
    # (api.openai.com, or the OPENAI_BASE_URL env var the SDK natively reads — the pre-existing
    # implicit OpenRouter path); "openrouter" falls back to https://openrouter.ai/api/v1.
    openai_base_url: str = ""
    # Default reasoning effort for the "openai"/"openrouter" provider, used only when a step
    # does not pass an explicit per-call effort. Blank (the default) keeps the pre-existing
    # behavior: no `reasoning_effort` is sent at all. Needed for mandatory-reasoning models
    # served over OpenRouter (e.g. z-ai/glm-5.3-flash): reasoning there cannot be disabled
    # (the endpoint 400s on `reasoning.enabled=false`), so with no effort hint the model
    # burns the whole `max_tokens` budget on reasoning tokens and returns EMPTY content —
    # which starves the small-budget steps (interview question/classify/recap at 200–300
    # tokens) and was observed live as interviews returning blank questions. "low" caps the
    # reasoning share so every step's budget reaches actual content; steps keep their
    # explicit-effort override either way (captain requirement: provider behaviour is
    # config, not edit).
    openai_reasoning_effort: str = ""
    # Model ID the step-tier map routes every step to when llm_backend == "openrouter" — the
    # OpenRouter slug for the same GLM-5 tier the bedrock backend uses, in OpenRouter's
    # vendor/model form. Overridable via OPENROUTER_DEFAULT_MODEL_ID; keep in lockstep with
    # the pricing entry (app/llm/pricing.py) or the cost readout shows 0.0 for it.
    openrouter_default_model_id: str = "z-ai/glm-5"

    # Emit per-call InferenceCostUSD custom metric to CloudWatch (CMW/Bedrock namespace) for the
    # non-technical cost dashboard. Default True so v1 launch has immediate visibility; flip to
    # False in settings to disable without code change (captain requirement that provider behaviour
    # is config, not edit). Research sidecar stays on Anthropic (carve-out) so is excluded; the
    # dashboard labels this prominently.
    emit_bedrock_cost_metrics: bool = True

    # --- Secrets shim config (app/secrets/) — selects how every secret *below* is resolved. ---
    # Left at "env" (process env / a local .env), docker compose and pytest need no cloud setup;
    # flipping to "aws"/"azure" for production is the only change needed. Shared verbatim with
    # web/'s Node resolver (web/lib/secrets/) so both runtimes behave identically.
    secrets_backend: str = "env"
    secrets_cache_ttl_seconds: float = 300.0
    # AWS SSM Parameter Store: every secret name below is read from "<prefix><NAME>".
    secrets_aws_ssm_prefix: str = "/newsroom/"
    # Azure Key Vault URL, e.g. "https://<vault-name>.vault.azure.net/".
    secrets_azure_vault_url: str = ""

    # --- Server-side-only secrets (never client-exposed). Placeholders for downstream tickets. ---
    # LLM: one company Anthropic key, called server-side, model-tiered by step (D14). Resolved
    # through the secrets shim — see the `anthropic_api_key` property below, not a field here.
    # OpenAI is the org's agent stack (§6); key lands here too. Resolved through the secrets shim
    # — see the `openai_api_key` property below, not a field here.
    # --- Green-connector credentials (server-side only, NEVER in the Source registry doc, D8/D14). ---
    # These are the *admin-provisioned* secrets the Green connectors read. They live here (env),
    # not in a Source doc: a Source carries only kind-specific config (folder ids, channel ids,
    # feed urls). Web/RSS needs no credential (public pull). See app/connectors/README.md for what
    # an admin must provision.
    #
    # Google Drive — recommended: server-side *incremental OAuth on the SSO (NextAuth Google)
    # identity* (open-decisions Item 6). A one-time consent grants an offline refresh token held
    # here; the connector exchanges it for short-lived access tokens at refresh time. (A
    # folder-scoped service account is the documented fallback for unattended refresh.) The same
    # grant also authorizes the finalize/review Google Docs export (app/render, app/review) — it
    # needs both the `drive.readonly` and `drive.file` scopes, not just the connector's read scope.
    # Resolved through the secrets shim like brain_repo_url/brain_deploy_key — see the properties
    # below, not fields here — so a rotated refresh token takes effect on the next cache TTL
    # without a redeploy.
    # Slack — a Slack app/bot token (scopes: channels:history, channels:read, groups:history).
    # The same app also carries the expert deep-link share (a UI concern); here it is read-only.
    # slack_bot_token is resolved through the secrets shim — see the property below.

    # Datastore: single MongoDB (Atlas) instance backs work-state + content lake (D3, D9, §6).
    # (mongo_url is resolved through the secrets shim — see the property below.)
    # Logical database name inside that instance (the compose URL already carries one; this is
    # the fallback + the knob the repository layer reads). Not a secret — a plain field.
    mongo_db_name: str = "content_machine"

    # --- Content lake / hybrid index (D9, §6). ---
    # Query backend for the hybrid index. "local" = the dependency-free fallback that runs against
    # plain community MongoDB (compose `mongo:7`) and the test double; "atlas" = push down to Atlas
    # Vector Search + Atlas Search in production. Flipping this is the only production change needed
    # (see app/lake/README.md). Kept "local" by default so dev/UAT/tests need no Atlas cluster.
    lake_index_backend: str = "local"
    # Embedding provider for the semantic leg. "hashing" = the deterministic local embedder (no key,
    # no network); a real provider slots in behind the same protocol when configured (D9).
    embedding_backend: str = "hashing"
    # Embedding vector width. Must match the Atlas vector-index definition in production.
    embedding_dim: int = 256

    # --- Git brain / content store (D1/D2/D4, §7). Brain lives in its own repo,
    # `HendoCode/content-machine-brain`, cloned read-write onto disk rather than baked in as a
    # subdirectory. ---
    # Filesystem root of the local brain clone (voices/personas/engine/piece folders). Git *is*
    # the versioning: read from here, and content revisions / transcripts / accepted lessons /
    # voice-kit edits are committed (and, when a remote is configured, pushed) here. Server-side
    # path only. Default assumes a sibling checkout, matching a developer's own manually-cloned
    # brain (the local-dev path — no BRAIN_REPO_URL needed in that case).
    brain_root: str = "../content-machine-brain"
    # Git remote URL to clone BRAIN_ROOT from when it doesn't exist yet (container / managed-host
    # boot) and to fast-forward-pull from on subsequent boots, picking up hand-nurtured brain
    # updates. An SSH URL (`git@github.com:HendoCode/content-machine-brain.git`) — left blank for
    # local dev, where BRAIN_ROOT already points at a clone the developer manages with their own
    # git (ambient SSH credentials, manual pull/push). Resolved through the secrets shim — see the
    # `brain_repo_url` property below, not a field here.
    #
    # Optional SSH deploy-key private key (repo-scoped, read-write, single-repo blast radius — the
    # least-privilege machine-push credential, and the reason this isn't a classic PAT) for
    # clone/pull/push against BRAIN_REPO_URL when no ambient SSH credential is available (e.g.
    # inside a container). Materialized as a process-local, mode-0600 key file for the lifetime of
    # the process (see app/git/ssh_auth.py) — never persisted to `.git/config` or the remote URL.
    # Also resolved through the secrets shim — see the `brain_deploy_key` property below.
    # Default identity stamped on machine-authored commits when the acting user is unknown.
    # A real acting user is passed per-commit for attribution (D15/§1.17).
    git_author_name: str = "newsroom-agent"
    git_author_email: str = "agent@newsroom.local"

    # --- Publish (finalized → published HITL button; app/publish/, docs/design.md D13 note). ---
    # NOT secrets — plain resource identifiers, not credentials. The bucket is generally public by
    # design (Hendo, v1) so there is no access-control value in hiding its name. Blank by default:
    # `/api/pieces/{id}/publish` 503s until a captain sets this (see infra/aws-poc/README.md).
    published_assets_bucket: str = ""
    published_assets_region: str = "us-east-1"

    # --- Per-piece Google Drive root folder (cmw-drive-named-folder-scoping; app/drive/). NOT a
    # secret — a plain folder NAME, same pattern as published_assets_bucket above. The app's
    # Google account owns (and, under drive.file scope, is the only thing that can see) this
    # named folder in its personal My Drive; this code finds-or-creates it itself under the
    # drive.file grant, so there is NO out-of-band Shared-Drive/content-manager provisioning
    # anymore. Blank by default (no-op): every caller must behave exactly as it did before this
    # ticket (Docs land loose at Drive root, no HTML/PDF Drive upload) rather than crash — see
    # app/drive/folder.py's `PieceDriveFolders.enabled`.
    google_drive_root_folder_name: str = ""

    # Build/test brain pin (agents/brain.lock, agents/app/git/README.md). NOT a secret — a plain
    # field. Unset (the runtime default): `ensure_brain_available` fast-forward-pulls the live
    # branch tip exactly as before — the running app keeps tracking + pushing to it. Set (build/
    # test tooling, sourced from brain.lock's `ref`): pins the clone to that exact commit/tag/
    # branch (fetch + detached checkout) instead of pulling, so building/testing against the brain
    # is reproducible and can't be broken by a same-day live-brain edit. Never default this to the
    # lockfile value here — that would silently pin runtime too.
    brain_ref: str = ""

    # --- Bounded autonomous council revision defaults (legacy pieces) ---------------------
    # ContentProject pieces inherit `council_policy` from the project. Legacy pieces (no
    # content_project_id) fall back to these defaults so the council step always has a policy.
    council_quality_bar: float = 9.0
    council_iteration_ceiling: int = 3
    council_cost_ceiling_usd: float = 25.0
    council_gaps_require_human: bool = True
    council_clearances_require_human: bool = True

    def default_council_policy(self) -> "CouncilPolicy":
        """Return a CouncilPolicy from settings for legacy pieces."""
        # Lazy import avoids any risk of an import cycle with content_workflow.
        from app.content_workflow.models import CouncilPolicy

        return CouncilPolicy(
            quality_bar=self.council_quality_bar,
            iteration_ceiling=self.council_iteration_ceiling,
            cost_ceiling_usd=self.council_cost_ceiling_usd,
            gaps_require_human=self.council_gaps_require_human,
            clearances_require_human=self.council_clearances_require_human,
        )

    # --- Per-run cost ceiling (D14, the one sanctioned hard stop) -------------------------
    # These bounds apply to every RunBudget created for batch chains, interview turns, and
    # lessons proposals. Defaults are generous (comfortably cover a normal run) but NOT infinite
    # — a genuine guard against runaway spend. Operators can tune via env without code change.
    # Any axis left at 0/None disables that specific bound; see RunBudget.__init__.
    run_budget_max_cost_usd: float = 2.0  # ~40x a typical $0.05 run
    run_budget_max_calls: int = 100  # ~10 interview turns + draft + council + incorporate
    run_budget_max_total_tokens: int = 1_000_000  # ~20 typical Opus calls

    def make_run_budget(self) -> "RunBudget":
        """Construct a RunBudget from the configured ceilings (D14)."""
        from app.llm.budget import RunBudget

        return RunBudget(
            max_calls=self.run_budget_max_calls if self.run_budget_max_calls > 0 else None,
            max_total_tokens=self.run_budget_max_total_tokens
            if self.run_budget_max_total_tokens > 0
            else None,
            max_cost_usd=self.run_budget_max_cost_usd if self.run_budget_max_cost_usd > 0.0 else None,
        )

    def _secret(self, name: str) -> str:
        """Resolve secret `name` through the configured `app.secrets` backend, defaulting to ""
        (matching this file's pre-shim empty-string defaults) when it isn't set."""
        provider = get_secrets_provider(
            backend=self.secrets_backend,
            ttl_seconds=self.secrets_cache_ttl_seconds,
            aws_ssm_prefix=self.secrets_aws_ssm_prefix,
            azure_vault_url=self.secrets_azure_vault_url,
        )
        try:
            return provider.get(name)
        except SecretNotFoundError:
            return ""

    @property
    def anthropic_api_key(self) -> str:
        return self._secret("ANTHROPIC_API_KEY")

    @property
    def mongo_url(self) -> str:
        return self._secret("MONGO_URL")

    @property
    def brain_repo_url(self) -> str:
        return self._secret("BRAIN_REPO_URL")

    @property
    def brain_deploy_key(self) -> str:
        return self._secret("BRAIN_DEPLOY_KEY")

    @property
    def openai_api_key(self) -> str:
        return self._secret("OPENAI_API_KEY")

    @property
    def slack_bot_token(self) -> str:
        return self._secret("SLACK_BOT_TOKEN")

    @property
    def google_oauth_client_id(self) -> str:
        return self._secret("GOOGLE_OAUTH_CLIENT_ID")

    @property
    def google_oauth_client_secret(self) -> str:
        return self._secret("GOOGLE_OAUTH_CLIENT_SECRET")

    @property
    def google_oauth_refresh_token(self) -> str:
        return self._secret("GOOGLE_OAUTH_REFRESH_TOKEN")

    def has_llm_credentials(self) -> bool:
        """True once a real provider key is configured. Used by /api/status to report
        readiness without ever leaking the key itself.

        Bedrock uses ambient IAM, not a key, so this method no longer treats the backend
        name alone as sufficient — a live provider object is the real readiness signal.
        """
        return bool(self.anthropic_api_key or self.openai_api_key)

    def has_mongo(self) -> bool:
        """True once a Mongo connection string is configured. Reported as a boolean readiness
        flag on /api/status — never the connection string itself (D14)."""
        return bool(self.mongo_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
