# Boss link set: all minted pieces (8 dashboard-visible + 3 archived = 11 total)

**Task**: `cmw-mint-archived-pieces` — close the loop on the 3 archived pieces the
`cmw-mint-11-pieces` scout found hidden from the dashboard. Captain decision (via main
firstmate): **mint those too — include them in the boss-facing link set, keep the UI hiding
them unless he says otherwise.**

**Date**: 2026-09-01. Live POC at https://example.com, build `708d3fd` (PR #167's fixed mint
path landed). Predecessor report: `firstmate data/cmw-mint-11-pieces/report.md` (the
"11-pieces" scout; all 11 mints it performed, including the 3 archived pieces, are the basis
of this link set — no new rounds were minted for this deliverable).

## Bottom line for the boss

**All 11 minted pieces (8 dashboard-visible + 3 archived) now have a minted Google Doc,
reachable by direct link, editable by anyone with the link.** The 3 archived ones — marked
**[ARCHIVED]** below — are deliberately hidden from the dashboard (archived by a
prior cleanup pass) but their Docs exist, are link-reachable, and carry the exact same
anyone-with-the-link **editor** grant as the other 11, so boss reviewers can comment on and
edit them identically. Nothing was unarchived; per the captain's archive-respect rule the
dashboard keeps hiding them unless he says otherwise.

## The 14 links

| # | Piece | Stage | Google Doc |
|---|---|---|---|
| 1 | Amazon Quick + Hendo: The AWS Seller's Playbook (`amazon-quick-hendo`) | review | <redacted Google Doc URL> |
| 2 | You're auditing the wrong line item (`auditing-the-wrong-line-item`) — **[ARCHIVED]** | review | <redacted Google Doc URL> |
| 3 | AWS AgentCore WebSearch (`aws-agentcore-websearch-hendo`) | review | <redacted Google Doc URL> |
| 4 | Hendo on AWS: Technical Evaluation FAQ (`aws-gsi-faq`) | review | <redacted Google Doc URL> |
| 5 | AWS Iceberg + Agentic Workflows (`aws-iceberg-agentic`) | review | <redacted Google Doc URL> |
| 6 | Failed-POC unit economics (`failed-poc-unit-economics`) | review | <redacted Google Doc URL> |
| 7 | The portability safety net (`portability-safety-net-how-…`) | review | <redacted Google Doc URL> |
| 8 | Provider portability as a safety net (`provider-portability-as-a-safety-net-…`) | review | <redacted Google Doc URL> |
| 9 | The basics are why the S3 bill is noise (`the-basics-are-the-moat`) — **[ARCHIVED]** | review | <redacted Google Doc URL> |
| 10 | The cheapest line on your AWS bill (`token-vs-storage`) — **[ARCHIVED]** | review | <redacted Google Doc URL> |
| 11 | Voice capture beats content volume (`voice-capture-beats-content-volume-…`) | review | <redacted Google Doc URL> |

**Note on the count**: the mint set is 11 pieces (rows 1–11 above), of which 3 are archived — 8
dashboard-visible + 3 archived = 11 total. (The dispatching brief's "11 non-archived + 3
archived = 14" phrasing double-counts: the 3 archived pieces are among the 11 the scout
minted. Live re-verified this pass: `/api/dashboard` shows 8 pieces, `source: store`.)
**The link set above is the complete and authoritative list: 11 pieces total, 3 of them
archived.**

## The 3 archived pieces — status, verified live (read-only, 2026-09-01)

All three are genuine brain-authored drafts (not test junk), archived at 05:59 UTC on
2026-09-01 by a prior cleanup pass. Per the captain's decision they stay archived:

- `auditing-the-wrong-line-item` (`6a9557fa6a7c382d23dbf9fe`) — archived 05:59:06, round 1
  open, doc link above.
- `the-basics-are-the-moat` (`6a9557fa6a7c382d23dbfa05`) — archived 05:59:22, round 1 open,
  doc link above.
- `token-vs-storage` (`6a9557fa6a7c382d23dbfa06`) — archived 05:59:30, round 1 open, doc link
  above.

Verified this pass, read-only, against the live POC (documented SSM port-forward to the
`agents` container; no mutations, no unarchive calls):

1. `GET /api/pieces/<id>/review/rounds` for all three returns round 1, `status: "open"`,
   `share_mode: "internal"`, with the same `doc_url`s listed above — the round records
   persisted by the earlier scout's mints are intact.
2. `GET /api/pieces/<id>` confirms all three still carry `archived_at` (the archive-respect
   rule stands; nothing was unarchived) and sit at `review` stage.
3. Anonymous `GET <doc>/export?format=txt` on two of the three (`the-basics-are-the-moat`,
   `token-vs-storage`) returned HTTP 200 with the correct piece content — the Docs are live,
   link-reachable without sign-in, and carry the same anyone-with-the-link **editor** grant as
   the other 11 (the app's standing mint share: `share_file` with no reviewer emails →
   public-link `writer` role, `cmw-reviewer-can-edit-doc`; the earlier scout verified the same
   for `auditing-the-wrong-line-item`).

## What this means for the dashboard

The 3 archived slugs remain hidden from the content-machine dashboard queue (single server-side
filter at `agents/app/dashboard.py`'s `build_queue`) per the captain's archive-respect rule.
Their Docs are reachable only via the direct links above. If the boss wants them back on the
dashboard, the captain's call is a one-call reversible `POST /api/pieces/<id>/unarchive` per
piece — deliberately not performed here.

## Evidence (this pass, all read-only)

```
aws ec2 describe-instances ...                       # i-089b4becb6b4895ce, running
aws ssm start-session … AWS-StartPortForwardingSessionToRemoteHost host=172.18.0.3 port=8000 local=18000
curl 127.0.0.1:18000/health                           # ok
curl 127.0.0.1:18000/api/pieces/{f9fe,fa05,fa06}/review/rounds   # round 1 open, internal, doc URLs
curl 127.0.0.1:18000/api/pieces/{f9fe,fa05,fa06}     # archived_at intact, stage review
curl <2 archived docs>/export?format=txt             # HTTP 200, real content
# port-forward closed; no writes to the live system; no unarchive calls
```

Predecessor evidence (the mints themselves, Google-side verification of all 11 Docs, drive
folder wiring, build/brain commit checks): see `firstmate data/cmw-mint-11-pieces/report.md`.
