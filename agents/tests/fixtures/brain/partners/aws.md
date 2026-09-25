# Partner Facts: AWS
last-verified: 2026-07-24 (agent stack checked against AWS release notes)
staleness-warning: AWS renames and reorganizes fast. Re-verify before any published
  piece. When in doubt, the persona should say "verify current naming," not assert.

## Agent stack (the part most relevant to the author's work)
- Amazon Bedrock AgentCore — the current platform to build/deploy/operate agents.
  GA across many regions as of mid-2026. Modular services usable together or alone:
    - AgentCore Runtime — session-isolated execution (Firecracker microVM), long-running
    - AgentCore Gateway — turns APIs / Lambda / MCP servers into agent-callable tools
    - AgentCore Identity — inbound/outbound agent auth
    - AgentCore Policy — Cedar-based access/authorization engine
    - AgentCore Memory — short- and long-term memory across sessions
    - AgentCore Managed Harness — GA at AWS Summit NY 2026. CreateHarness/InvokeHarness;
      defines agent by model+prompt+tools, runs the full loop, model-agnostic, mid-session
      model switching. Reduces scaffolding to ~two API calls.
    - Built-in tools: Code Interpreter, Browser, managed Web Search (zero data egress)
    - AgentCore Evaluations — continuous quality assessment against production traffic
  Works with open-source frameworks: Strands, LangGraph, LlamaIndex, CrewAI, Google ADK,
  OpenAI Agents, LangChain.
- Amazon Bedrock Agents Classic — the OLD (Nov 2023) Bedrock Agents, RENAMED. Closed to
  new customers July 30, 2026. Do NOT call this just "Bedrock Agents" in new content;
  that name now points at the Classic/legacy thing. Steer to AgentCore.
- Also announced 2026 (verify specifics before use): AWS Context, AWS Continuum, Amazon Quick.

## Foundation / platform
- Amazon Bedrock — managed access to foundation models; guardrails; multi-agent collaboration.
- Amazon SageMaker — ML platform (verify current sub-product naming before citing).

## Naming traps to catch in drafts
- "Bedrock Agents" now means the legacy Classic product. New work = AgentCore.
- Don't invent AgentCore sub-services not listed here — flag as "verify" instead.

## Positioning the AWS field team endorses
- Security enforced at the infrastructure layer "agents can't bypass."
- "Any framework, any model." Open-source flexibility + enterprise security.
- Prototype-to-production speed. Human-in-the-loop / control balanced with autonomy.
