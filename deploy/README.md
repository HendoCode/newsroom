# Security-scan deploy gate

A mandatory Trivy scan gate in front of `tofu apply` for the AWS POC (`infra/aws-poc/`). Manually
triggered — there is no CI loop here — but it's a hard precondition in *code*, not just
documentation: `deploy/deploy.sh` refuses to reach the apply step unless `deploy/security-gate.sh`
exits 0.

**Captain-decided scope** (this ticket): images + IaC + secrets, all three via Trivy (already
installed on the operator machine). **Threshold: block on CRITICAL only** for images and IaC.
Secrets are the one exception — **any** secret finding blocks, regardless of severity, since a
leaked credential doesn't have a "low severity" version.

## Files

- **`security-gate.sh`** — runs all three scans, prints a PASS/FAIL line per scan, and exits
  nonzero if any of them fail.
- **`deploy.sh`** — the deploy wrapper. Runs `security-gate.sh` first; only on a green gate does it
  print the `tofu apply` command to run next. It never runs `tofu apply` itself.
- **`trivy-secret.yaml`** — Trivy secret-scanner config; see "Secrets and env-var interpolation"
  below.

## What each scan covers

1. **Images (CVE)** — `trivy image --severity CRITICAL --ignorefile agents/.trivyignore` against
   the two real ECR images the deploy pulls:
   `<AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/cmw-poc-{web,agents}`. Defaults to the `:latest`
   tag (what `infra/aws-poc`'s deploy actually pulls — see its README's "Redeploying just an
   app-code change"); pass a plain tag or a `sha256:...` digest as `$1` to scan a specific build
   instead:
   ```
   ./deploy/security-gate.sh bc3419e
   ./deploy/security-gate.sh sha256:d61526f946730618ea8f662726c94cc1b915df124d3603a06aee57b5d0f9430e
   ```
   Trivy authenticates to ECR itself via the ambient AWS credential chain — no `docker login`
   needed. The operator just needs valid AWS credentials in the environment first (e.g.
   `aws configure export-credentials` into env vars, or any other route into the standard AWS SDK
   credential chain). `agents/.trivyignore` is the existing accepted-CVE list (Debian
   base-OS packages with no fix upstream — see that file's own header and root `AGENTS.md`'s Sharp
   Edges).

2. **IaC (misconfig)** — `trivy config --severity CRITICAL` against every directory in the tracked
   tree containing a `.tf` file (discovered via `git ls-files '*.tf'`, not hardcoded — a future new
   TF directory needs no gate-script edit). Each directory's own `.trivyignore`, if present, is
   passed explicitly (`--ignorefile <dir>/.trivyignore` — Trivy's own `.trivyignore`
   auto-discovery is relative to the caller's CWD, not the scanned target directory, so this has to
   be explicit). `infra/aws-poc/.trivyignore` carries the one currently-accepted finding
   (AVD-AWS-0104, the security group's open egress — see that file for the justification).

3. **Secrets** — `trivy fs --scanners secret` (no severity filter — any finding blocks) over a
   `git archive` snapshot of the **tracked** tree, not the raw working directory. Scanning the
   working tree directly would also sweep in gitignored build output (`web/.next`, `node_modules`,
   etc.) — slower and not representative of what actually ships. Uses `trivy-secret.yaml` (see
   below).

## Secrets and env-var interpolation

The compose files (`docker-compose.yml`, `infra/aws-poc/templates/docker-compose.prod.yml.tpl`)
reference secrets via shell/Terraform interpolation — `${ANTHROPIC_API_KEY:-}`, the
Terraform-escaped `$${NEXTAUTH_SECRET}` — never a literal value. Empirically verified (2026-08-12,
against the real tracked tree, see the smoke-run below) that Trivy's built-in rules do **not**
currently flag these patterns. `trivy-secret.yaml` adds a defensive `allow-rule` matching exactly
that interpolation syntax anyway, so a future change to Trivy's built-in ruleset can't silently
turn an env-var *reference* into a blocking finding — a real secret sitting next to one is still
caught, since the rule only matches the interpolation syntax itself.

Separately, worth knowing if you're ever debugging "why didn't this get flagged": Trivy's secret
scanner has its own built-in allow-rules (`pkg/fanal/secret/builtin-allow-rules.go` upstream) that
skip any path containing `test`/`example` (case-insensitive, as a path-segment-ish match) and any
`.md` file, by design, to cut noise from fixture/doc files. None of this repo's real committed
compose/TF files match those patterns — it only bit us once, while hand-testing this gate (see the
smoke-run below).

## Fail-closed behavior

This is the actual hard requirement, not just aspiration: a missing scanner, a scan error, or an
unreachable target must **block**, never pass silently.

- `security-gate.sh` checks `trivy` and `git` are on `PATH` before attempting anything — missing
  either exits 1 immediately with a clear message.
- Every scan uses `--exit-code 1`, so Trivy's own execution errors (auth failure, unreachable ECR,
  a bad tag) produce the *same* nonzero exit as a real finding — the gate doesn't try to
  distinguish "couldn't scan" from "found a problem"; both block.
- The `git archive` snapshot step is a hard precondition for the secrets scan — if it fails, that
  scan is recorded as FAIL, not skipped.
- The gate runs all three scan categories regardless of earlier failures (so the summary always
  reports all three), then exits 1 if *any* category failed.

## Smoke run (2026-08-12)

Ran directly against the real ECR images, the real `infra/aws-poc`/`infra/aws-poc-state-backend`
Terraform, and this repo's real tracked tree — nothing mocked.

**Full run against `:latest` (what a real deploy would pull today):**

```
==> image: cmw-poc-web:latest
==> image: cmw-poc-agents:latest
==> iac: infra/aws-poc
==> iac: infra/aws-poc-state-backend
==> secrets: tracked tree

================ Security gate summary (severity: CRITICAL-only, secrets: any) ================
FAIL  image: cmw-poc-web:latest  (exit 1)
PASS  image: cmw-poc-agents:latest
PASS  iac: infra/aws-poc
PASS  iac: infra/aws-poc-state-backend
PASS  secrets: tracked tree
======================================================================================
RESULT: FAIL — deploy blocked. Fix the finding(s) above, or add a justified, commented
ignore entry (agents/.trivyignore for images, infra/aws-poc/.trivyignore for IaC) for an
accepted risk, then re-run.
```

**This is a real, current finding, not a fabricated demo**: `cmw-poc-web:latest` has one unignored
CRITICAL — `CVE-2026-59873` (tar: node-tar DoS via crafted gzip bomb) in the `tar` package bundled
inside `npm` itself, in the image's Node.js base layer (`usr/local/lib/node_modules/npm/...`), not
in this app's own code. It has a fix upstream (7.5.19; installed is 7.5.11). An older tagged build
(`:f7ba899`) is worse — it predates the P0 Next.js CVE patch (`#96`) and has 3 unignored CRITICALs.
No image tag currently available in ECR passes the image scan clean. This is exactly the kind of
thing this gate exists to catch before a deploy ships it — it was not remediated as part of this
PR (rebuilding/pushing new images is outside this ticket's "author the gate" scope and touches the
real ECR repos), but it should be rebuilt against a current `npm`/base image before the next real
apply.

**Agents image, IaC, and secrets scans are genuinely clean** — re-run in isolation:

```
$ trivy image --severity CRITICAL --exit-code 1 --ignorefile agents/.trivyignore \
    <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/cmw-poc-agents:latest
... exit=0, 0 unignored CRITICALs
```

**Fail-closed — missing scanner** (`trivy` removed from `PATH`):

```
$ PATH="/usr/bin:/bin" ./deploy/security-gate.sh
FAIL: trivy is not installed / not on PATH.
A missing scanner blocks the gate — this is not a skippable step.
$ echo $?
1
```

**Fail-closed — unreachable target** (nonexistent tag, simulating an ECR/registry failure):

```
$ ./deploy/security-gate.sh this-tag-does-not-exist-xyz
...
FAIL  image: cmw-poc-web:this-tag-does-not-exist-xyz  (exit 1)
  MANIFEST_UNKNOWN: Requested image not found
FAIL  image: cmw-poc-agents:this-tag-does-not-exist-xyz  (exit 1)
  MANIFEST_UNKNOWN: Requested image not found
...
RESULT: FAIL
$ echo $?
1
```

**Fail-closed — injected secret** (a throwaway commit adding a file with a fake GitHub PAT-shaped
token, reverted immediately after — never landed on this branch):

```
$ ./deploy/security-gate.sh
...
FAIL  secrets: tracked tree  (exit 1)
  CRITICAL: GitHub (github-pat) — GitHub Personal Access Token
  injected-credentials.txt:1
...
RESULT: FAIL
$ echo $?
1
```

**Deploy wrapper, isolated pass-through check** (a throwaway stub gate that just `exit 0`, to prove
`deploy.sh`'s "only print the apply command on a green gate" logic without needing a genuinely
clean image to exist):

```
$ ./deploy.sh my-test-tag
fake gate: PASS

Security gate PASSED.

This wrapper does not run the apply itself. From .../infra/aws-poc, run:

    cd infra/aws-poc && tofu apply
...
$ echo $?
0
```

## Usage

```
# Gate only (read-only — safe to run anytime):
./deploy/security-gate.sh              # scans :latest
./deploy/security-gate.sh bc3419e      # scans a specific tag/digest

# Gate + print the next apply command (never runs tofu apply itself):
./deploy/deploy.sh
```

See `infra/aws-poc/README.md`'s "Apply sequence" for the full deploy sequence this gate sits in
front of.
