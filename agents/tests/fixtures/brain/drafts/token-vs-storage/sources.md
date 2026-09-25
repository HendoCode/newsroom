# Sources & Handoff — Spike #4

Everything the draft rests on, with citations, plus the council record and the pre-publish
checklist. Written so you can edit the draft directly without losing the provenance.

## Research citations (all figures in the draft trace here)

**AWS S3 & data-transfer pricing**
- S3 Standard $0.023/GB-month (first 50 TB); 10 TB ≈ $230/mo — https://www.cloudzero.com/blog/s3-pricing/
- Egress $0.09/GB (past first 100 GB/mo); egress ~40% of bills; bills 2–3x pricing page —
  https://www.cloudseedrive.com/s3-data-transfer-fees/ · https://leanopstech.com/blog/aws-s3-pricing-2026/
- Same-region S3→service (EC2/Lambda/Bedrock/etc.) transfer is free —
  https://blog.besharp.it/aws-data-transfer-costs-in-a-nutshell/
- S3 gateway endpoint free, no data charge, stays on AWS private net; NAT path $0.045/GB —
  https://oneuptime.com/blog/post/2026-02-12-optimize-data-transfer-costs-with-vpc-endpoints/view
- Gateway endpoint route-table gotcha (traffic falls to NAT if route table not associated) —
  https://oneuptime.com/blog/post/2026-02-12-set-up-vpc-gateway-endpoints-s3-dynamodb/view
- Gateway endpoints same-region only; cross-region → NAT or PrivateLink ($0.01/hr/AZ) —
  https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html ·
  https://repost.aws/articles/ARjzluyMS8RbeOOK4MGXRG6Q/cost-effective-methods-for-accessing-s3-buckets-cross-region

**Token / inference pricing**
- Claude Opus 5 (released 2026-07-24) $5 in / $25 out per M tokens; GPT-5.5 $8.44 in / $2.81 out —
  https://www.cloudzero.com/blog/anthropic-claude-api-pricing/ · https://promptcost.org/en/blog/gpt-55-pricing-guide-2026/
- One Sonnet support app ≈ $29,800/mo; enterprise API bills $50K–$1M+/mo; RAG 3–5x tokens —
  https://medium.com/aigenverse/why-most-enterprises-underestimate-the-real-cost-of-llm-inference-in-production-9b675adf7860 ·
  https://www.cloudzero.com/blog/inference-cost/

**Vector store pricing**
- 10M vectors: managed DB $850–$5,000+/mo; raw S3 vectors ~$1.38/mo —
  https://www.exploreagentic.ai/insights/s3-vectors-enterprise-rag/ · https://mixpeek.com/guides/vector-database-cost-comparison

**Failed-POC economics**
- 95% pilots no P&L impact; $30–40B invested — https://www.forbes.com/sites/jasonsnyder/2025/08/26/mit-finds-95-of-genai-pilots-fail-because-companies-avoid-friction/
- Failed AI project avg $6.8M cost / $1.9M return; 3–5x overrun — https://coworker.ai/blog/why-enterprise-ai-fails
- Gartner 30% abandoned after POC — https://www.gartner.com/en/newsroom/press-releases/2024-07-29-gartner-predicts-30-percent-of-generative-ai-projects-will-be-abandoned-after-proof-of-concept-by-end-of-2025

**Canonical AWS RAG pattern (basis for the diagram)** — https://aws.amazon.com/blogs/big-data/build-scalable-and-serverless-rag-workflows-with-a-vector-engine-for-amazon-opensearch-serverless-and-amazon-bedrock-claude-models/

## Council record (final)
Slop-Allergist 9 · Voice-Guardian 9 · Technical-Reviewer 9 · Specificity-Auditor 9 ·
Partner-Brand-Steward/AWS 9–10 · Closer 9. Aggregate ≥ 9 (clears the bar). The one soft spot:
the direct-vs-Bedrock paragraph scores 8 until a real cost number is attached.

## Pre-publish checklist (before you push it live)
1. [GAP] Add a first-hand instance — a POC you saw die or an inference bill that blew past
   forecast, with a rough dollar/engineer-week figure. Turns a well-sourced argument into a
   first-hand one.
2. [GAP] Add a real direct-vs-Bedrock cost number to the flexibility paragraph, or accept it
   as a claim.
3. Clearance: may we name Dairyland Power, or anonymize to "a US energy cooperative"?
4. Re-verify AWS pricing/naming at publish time — AWS renames and reprices fast.

## After you publish
Come back and run Step 6 (Lessons): I diff your published version against the draft, propose
generalizable lessons, and on your yes append them to voice/<active-voice>/content-lessons.md.
