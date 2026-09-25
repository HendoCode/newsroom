# Sources & Handoff — aws-gsi-faq

## Provenance
Every answer traces to the call log in `transcript.md` (AWS agent-platform technical deep
dive, 22 July 2026). AWS-native technical claims are cited to AWS documentation; where a
claim needs an owner to confirm, it's marked [GAP] below.

## Positioning guardrail (hard constraint, verified against the draft)
Lead AWS-native (Bedrock, AgentCore, customer VPC, SageMaker). No cloud-agnostic capability,
Google, or Azure surfaced. LangGraph/LangChain appear only as frameworks the platform is
independent of — reassurance for the AWS SA, not a portability pitch.

## Open GAPs — each still needs owner sign-off
- [A4] CloudWatch answer written from AWS docs (native OTLP + AgentCore Observability).
  Follow-up: confirm which signals the container runtime emits vs. the AgentCore path.
- [A1] The full customer-POV architecture diagram is confidential — needs the owner's
  confirmation + clearance before embedding/sharing externally.

## Research citations — AWS-native facts used to firm the answers
- CloudWatch OTLP endpoints (traces/logs) — https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLPEndpoint.html
- CloudWatch native OTEL metrics + PromQL, GA mid-2026 — https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-cloudwatch-otel-metrics/
- Bedrock AgentCore Observability — https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/observability.html
- Bedrock AgentCore Runtime — https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-how-it-works.html
- Bedrock Agents (Classic) closing to new customers 30 Jul 2026 — https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html

## Clearance before written use
- Naming the customer names said verbally during the call in a persistent artifact.

## Pre-publish checklist
1. Close or explicitly accept each [GAP] above.
2. Get the clearance.
3. Re-verify AWS service names at send time.
4. Strip the .editorial block from draft.html.

## Council record
- slop-allergist 9 · voice-guardian 9 · specificity-auditor 9 · technical-reviewer 9 ·
  partner-brand-steward/AWS 9. Aggregate ≈ 9.0 — clears the bar.
- Residual (not blocking; tracked as follow-ups/verifies): the open GAPs, the clearance,
  and the AWS service-name verifications.
