# Interview Transcript — Spike #4 (token cost vs. storage cost, drawn to scale)

Source material for the token-vs-storage piece. Per the Content Machine flow, the draft
traces back to this transcript. Several answers were supplied from research (the author
directed "give the answer from research" / "research this") rather than from the author's
own lived experience — those are marked [RESEARCH-DERIVED]. This is why the draft still
carries a [GAP] for a first-hand instance.

Roster run: Ferriss, Skeptic, King (first sitting); Architect, Operator, Partner-Advocate/AWS
(second sitting).

---

## Ferriss

**Q1 — What's the real storage workload and its monthly S3 bill?**
[RESEARCH-DERIVED] Anchor: ~10 TB in S3 Standard ≈ $230/month, ~$2,760/year; 1 TB ≈ $23/month.

**Q2 — One real instance of GenAI money going up in smoke (dollars or engineer-weeks)?**
[RESEARCH-DERIVED] MIT State of AI in Business 2025: 95% of GenAI pilots delivered no
measurable P&L impact against ~$30–40B invested. Gartner: 30%+ of GenAI projects abandoned
after POC. Completed-but-failed enterprise AI project averages $6.8M cost / $1.9M return
(-72% ROI); implementations run 3–5x initial estimate. [GAP remains: author's own witnessed
instance — not supplied.]

## Skeptic

**Q1 — Strip out headcount; is infrastructure-only GenAI spend still orders of magnitude
above the S3 bill, or is the comparison rigged by smuggling salaries into one side?**
[RESEARCH-DERIVED] Like-for-like, infra only: one production support app on Claude Sonnet
≈ $29,800/month in tokens; enterprise API bills $50K–$1M+/month; RAG burns 3–5x the tokens
of a plain query. Vector DB (10M vectors) $850–$5,000+/month vs. the same as raw S3 vectors
at $1.38/month. Verdict: comparison holds WITHOUT headcount (tokens alone ~130x the S3 bill);
but the "$6.8M failed POC vs. one year of S3" framing IS rigged (project cost vs. line item)
and must not be the headline. Lead with recurring-vs-recurring ($29,800/mo tokens vs $230/mo
storage); keep $6.8M as supporting.

## King

**Q1 — If S3 is so cheap, why is it called the most expensive storage on earth?**
[RESEARCH-DERIVED] Not the storage — egress. Internet data-transfer-out is $0.09/GB (vs
$0.023 to store), scales with app activity not volume, can be 40% of an S3 bill, #1 cause of
bills landing 2–3x the pricing page. (Later refined: the fear is real for internet/cross-region
traffic but does NOT apply to an in-region pipeline — see Operator + the draft's egress section.)

## Architect

**Q1 — Draw the boxes and arrows: raw data in S3 to a token from the model; where does the
vector store sit; what issues the retrieval call?**
Not answered by the author (author noted he "goofed the architect answer"). Resolved instead
by research + a crafted AWS-style diagram following the canonical AWS RAG pattern: S3
(documents) → Lambda chunk/embed via Bedrock → vector store (OpenSearch Serverless / S3
Vectors) → retrieval → Bedrock (or direct) model → response, all in-region, S3 reached via
VPC gateway endpoint.

## Operator

**Q1 — Step one to build the in-region gateway-endpoint pipeline, and the one gotcha that
quietly puts the internet back in the data path?**
[RESEARCH-DERIVED] Step one: create the S3 gateway endpoint AND associate it with the route
table of every subnet the inference runs in. Gotcha #1 (route-table association): a subnet
whose route table lacks the endpoint's prefix-list route silently sends S3 traffic through the
NAT gateway — $0.045/GB, no error, forever. Verify the prefix-list entry on each subnet.
Gotcha #2 (cross-region): gateway endpoints are same-region only (route-table based); a bucket
in a different region than the VPC falls back to NAT, or requires interface endpoints/PrivateLink
($0.01/hr/AZ + data processing). Rule: same region, and verify the route-table association.

## Partner-Advocate (AWS)

**Q1 — Is AgentCore part of the architecture, or is a separate control plane doing that job,
making AgentCore a competing layer to leave out?**
[AUTHOR, in his own words] You can enable calling foundation models directly, or using them
through Bedrock. The key is the real flexibility AWS brings — the freedom to focus on the
outcomes and pick the cost winner for each workload, too. (Resolved the AgentCore question:
not a competing layer; the flexibility framing is stronger. [GAP: no concrete direct-vs-Bedrock
cost number yet.])
