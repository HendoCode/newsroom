# aws-poc OpenTofu state backend (bootstrap)

Creates the S3 bucket that `infra/aws-poc`'s own OpenTofu state lives in, plus the safety controls
around it (versioning, blocked public access, default encryption, deny-insecure-transport policy).

## Why this is a separate stack

`infra/aws-poc`'s state cannot describe the bucket it is stored in — applying that config would
need the bucket to exist before the backend can initialize, and the backend can't initialize until
the bucket exists. This stack breaks that cycle: it is applied **once, by hand, before**
`infra/aws-poc` is pointed at a remote backend, and essentially never touched again afterward.

Its own state stays **local** (gitignored, like `infra/aws-poc`'s state was before this migration)
for the same reason a backend-hosting bucket can't describe itself: this is a small, rarely-changed
stack, and putting its state in yet another bucket would just move the chicken-and-egg problem
somewhere else. Keep this stack's `terraform.tfstate` wherever `infra/aws-poc`'s state was
previously kept (the single durable operator checkout) and treat it with the same care.

## Locking

OpenTofu 1.10+ supports native S3 state locking via conditional writes (`use_lockfile = true` in a
`backend "s3"` block) — no DynamoDB table required. `infra/aws-poc/versions.tf`'s backend block uses
this. Re-check `tofu version` before assuming it's available if the pinned version ever moves
below 1.10.

## Apply sequence

```sh
cd infra/aws-poc-state-backend
tofu init
tofu plan   # review: should show only new resources (the bucket + its sub-resources), never a
            # change to anything in infra/aws-poc
tofu apply
tofu output bucket   # feed this into infra/aws-poc/versions.tf's backend "s3" bucket = "..."
```

Then, in `infra/aws-poc`, add/update the `backend "s3" { ... }` block with that bucket name and
run `tofu init -migrate-state` (see `infra/aws-poc/README.md` — "State").

## Teardown

Don't. `aws_s3_bucket.tofu_state` has `prevent_destroy = true` deliberately — destroying it while
`infra/aws-poc` still points at it as its backend would strand that stack's state. If this bucket
is ever genuinely retired, first migrate `infra/aws-poc` off it, then remove the lifecycle guard as
a deliberate, separate step.

## Protecting this stack's own state (deliberately unprotected, on purpose)

This stack's own `terraform.tfstate` stays local (see above) — no remote backend, no versioning,
no automatic backup. That's a considered tradeoff, not an oversight: every resource this stack
describes is a real, standing AWS object (the bucket + its policy/encryption/versioning/
public-access-block sub-resources). Losing this file never loses data or infrastructure — it only
orphans the bucket from tofu's bookkeeping, which a re-import fixes. So the protection that matters
here is a **tested recovery procedure**, not a backup.

**Why not just commit the state file?** It looks inert (it only "describes a bucket"), but it
isn't quite: `data.aws_caller_identity.current` puts the ARN and IAM user-id of whoever last ran
`tofu apply`/`plan` here into the state in plaintext — that's the applying human's identity, not a
bucket detail. Don't commit this file as-is, and don't hand-edit a copy to strip that resource out
either (state surgery is its own hazard) — re-check this reasoning before revisiting the idea.

**Why not a second bucket / different backend?** That just relocates the same chicken-and-egg
problem this stack exists to break (see "Why this is a separate stack" above), for no reduction in
actual risk — the resources are already durable in AWS regardless of where the *description* of
them lives.

### Recovering a lost state file

```sh
cd infra/aws-poc-state-backend      # from the single durable operator checkout — see project AGENTS.md
tofu init                            # local backend, starts from empty state

BUCKET="cmw-aws-poc-tofu-state-<your-account-id>"   # aws sts get-caller-identity if unsure

tofu import aws_s3_bucket.tofu_state "$BUCKET"
tofu import aws_s3_bucket_policy.tofu_state_require_tls "$BUCKET"
tofu import aws_s3_bucket_public_access_block.tofu_state "$BUCKET"
tofu import aws_s3_bucket_server_side_encryption_configuration.tofu_state "$BUCKET"
tofu import aws_s3_bucket_versioning.tofu_state "$BUCKET"

tofu plan   # expect "No changes" — if it shows any, investigate before applying anything
```

`data.aws_caller_identity.current` needs no import step; data sources populate on the next
refresh/plan. All 5 managed resources import by the bucket name alone (every sub-resource's id
*is* the bucket name).

Tested for real against the live bucket on 2026-08-07 (fresh scratch working directory, real AWS
credentials, no changes to the actual bucket): all 5 imports succeeded and the follow-up `tofu
plan` reported zero drift against the resources `infra/aws-poc` is actively using as its backend.
This procedure is proven, not just described — re-run it for real if it's ever actually needed,
don't assume this README still matches reality by the time it is.
