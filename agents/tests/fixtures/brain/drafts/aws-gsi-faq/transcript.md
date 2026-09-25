# Source — AWS Technical Evaluation Question Log

SOURCE for the aws-gsi-faq piece. Every FAQ answer must trace back to something here (or a
verified citation in sources.md). Captured from the call notes, not invented.

- Origin: Google Doc "AWS_Tech_Eval_Questions" (Tab: AWS Technical Evaluation: Question Log)
- Call: AWS agent-platform technical deep dive, Wed 22 July 2026
- AWS attendees: partner solutions architects and an AI/ML specialist SA
- Vendor attendees: demo-dana, the solutions architect, the technical lead, demo-mira
- Purpose: the AWS partner team's technical sign-off before exec meetings proceed.

## POSITIONING GUARDRAIL (applies to every answer — hard constraint)
Lead AWS-native: Bedrock, AgentCore, customer VPC, SageMaker. Do NOT surface cloud-agnostic
capability, Google, or Azure in written material going to this team.

## Open items — highest priority
- **A1 — Standard architecture diagram from the customer's POV**, showing the compute
  footprint when deployed in their VPC. Explicit ask for a shareable artifact. Deferred to
  the next call — a deliverable, not just an answer.
- **A4 — Performance monitoring integration with AWS services.** Does it integrate with
  AWS monitoring if the customer wants it? CloudWatch was referenced specifically. Needs a
  concrete CloudWatch / native AWS observability answer.

## Answered cleanly — just needs writing up
- **Deployment default:** container is the default; the whole platform is containerized. For
  the agent runtime, container or Bedrock AgentCore runtime are both options.
- **Consumption:** a hosted tier exists for education and startups on free credits only; ~99%
  of customers run deployed inside their own AWS VPC — the default and only commercial focus.
- **Ownership:** the customer owns their agents, knowledge bases, and workflows outright; the
  core runtime and framework are open source.
- **Observability:** OpenTelemetry into CloudWatch natively, plus AgentCore Observability by
  default on the Bedrock AgentCore runtime.
- **Compute footprint:** the platform runs entirely in the customer VPC across managed AWS
  services (DocumentDB, Aurora PostgreSQL, OpenSearch, S3, ElastiCache).

## Work split + notes
- Architecture/orchestration depth: the technical lead (with the AWS technical lead)
- Write-ups: demo-mira
- Reference architecture + CloudWatch observability: the infrastructure lead (infra lead)
- Pricing/licensing: the solutions architect
- The AWS technical lead asked about orchestration three times before satisfied — most
  technically demanding, over-prepare.
