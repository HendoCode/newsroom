# Amazon Bedrock AgentCore — FAQ Reference

Source: https://aws.amazon.com/bedrock/agentcore/faqs/
Note: Content below is paraphrased from the original AWS page, not copied verbatim.

## General

### What is Amazon Bedrock AgentCore?
A platform for building, connecting, and optimizing AI agents at production scale. It works with any open-source agent framework and any model, includes built-in authentication and access controls for connecting agents to tools and data, and provides tracing/evaluation for monitoring agents in production. AWS positions it as handling the infrastructure layer so developers can focus on agent logic while still getting enterprise-grade security and reliability.

### Who is AgentCore designed for?
Organizations and developers moving agents from proof-of-concept (built on open-source or custom frameworks) into production, who need reliable infrastructure, behavior monitoring, tooling, and flexibility as their agent use cases evolve.

### What capabilities does AgentCore provide?
A set of composable services usable independently or together:
- Runtime — serverless environment for deploying/scaling agents
- Memory — managed short- and long-term agent memory
- Gateway — turns APIs/Lambda functions into agent-usable tools and connects to MCP servers
- Browser — cloud-based browser runtime for web interaction
- Code Interpreter — secure sandboxed code execution
- Identity — secure access to AWS and third-party resources
- Observability — visibility into agent workflows for tracing/debugging
- Evaluations — ongoing quality monitoring and scoring
- Optimization — turns production traces into improvement recommendations
- Policy — governs what actions agents can take
- Agent Registry (Preview) — discovery/governance catalog for agents, tools, and skills
- Payments (Preview) — lets agents autonomously pay for resources via third-party wallets

### Which agent frameworks does AgentCore support?
Any open-source or custom framework, explicitly including CrewAI, LangGraph, LlamaIndex, Google ADK, OpenAI Agents SDK, and Strands Agents.

### What open-source protocols does AgentCore support?
Model Context Protocol (MCP) and Agent-to-Agent Protocol (A2A). A2A is currently available in Runtime, with wider support across other services planned.

### Which foundation models can I use?
Any model, in or outside Amazon Bedrock — including OpenAI, Google Gemini, Anthropic Claude, Amazon Nova, Meta Llama, and Mistral.

### How does Strands Agents integrate with AgentCore?
Strands Agents handles planning/reasoning/tool-use and connects to AgentCore services (Gateway, Memory, etc.) through a simple SDK, letting developers deploy agents with minimal code.

### Which regions is AgentCore available in?
Fifteen AWS regions: Mumbai, Seoul, Singapore, Sydney, Tokyo, Canada Central, Frankfurt, Ireland, London, Paris, Stockholm, São Paulo, US East (N. Virginia), US East (Ohio), and US West (Oregon).

### How does AgentCore accelerate agentic AI development?
By removing months of infrastructure build-out — a few lines of code connect any framework and model to a fully managed, auto-scaling platform, letting teams focus on agent behavior instead of backend engineering.

### I'm using Amazon Bedrock Agents today — should I switch to AgentCore?
You can keep using Bedrock Agents. AgentCore is described as a broader platform offering open-source framework support, model flexibility, MCP-based tool access, VPC connectivity, and A2A inter-agent communication, built from the same underlying service set (Runtime, Memory, Gateway, Browser, Code Interpreter, Identity, Policy, Observability, Evaluations) aimed at scaling agents into production.

### Does AgentCore offer VPC connectivity?
Yes, across Runtime, Memory, Gateway, Browser, Code Interpreter, Identity, and Observability, allowing agents to securely reach resources inside a private network.

## Runtime

### What is AgentCore Runtime?
A secure, serverless runtime for deploying and scaling agents built on any framework, protocol, or model. Supports direct code upload or container-based deployment, multimodal/multi-agent A2A workflows, and bi-directional streaming for real-time, interruptible conversations (useful for voice agents). Scales automatically from zero to thousands of concurrent sessions, with per-session isolation and VPC connectivity.

### What are the key benefits of AgentCore Runtime?
1. **Faster time to market** — deploy via container or direct code upload, with native MCP/A2A support.
2. **Elastic scaling for varied workloads** — handles both low-latency interactive sessions and long-running asynchronous work (up to 8 hours), plus bi-directional streaming; scales automatically without capacity planning.
3. **Enterprise security/compliance** — dedicated per-session compute, VPC/PrivateLink support, and integration with identity providers (Cognito, Entra ID, Okta) plus credential management for downstream services.
4. **Consumption-based pricing** — you're billed only for active CPU/memory use, not idle I/O-wait time, which AWS notes can account for 30–70% of typical agent workload time.

## Gateway

### What is AgentCore Gateway?
A unified endpoint that lets agents discover and securely connect to tools. It converts APIs and Lambda functions into agent-usable tools, connects to existing MCP servers, and enforces access via native IAM and OAuth. Offers one-click integrations for tools like Salesforce, Slack, Jira, Asana, and Zendesk.

### What are the key benefits of AgentCore Gateway?
1. **Unified tool access** — combine APIs, Lambda functions, and MCP servers behind one secured endpoint.
2. **Simplified integration** — turn existing resources into agent-ready tools in a few lines of code, with prebuilt connectors to popular enterprise tools.
3. **Scalable tool discovery** — built-in semantic search helps agents find the right tool as the tool catalog grows.

### How does Gateway help with tool selection and filtering?
Semantic search surfaces the most relevant tools for a given task, and metadata-based filtering (e.g., by risk level) controls which tools are accessible.

### What types of tools can I use with Gateway?
AWS services (S3, DynamoDB, Aurora, Redshift, Lambda), prebuilt connectors (web search, Bedrock Knowledge Bases), third-party services, and custom tools defined via API specs, function code, MCP servers, OpenAPI, Smithy, Lambda, or container images (ECR).

### What security measures does Gateway provide?
Multiple auth methods (IAM, OAuth 2.1, API keys), secure credential exchange between identity providers, detailed authentication/invocation visibility via Observability, and web application firewall support with configurable ACLs.

### How does Gateway work with other AgentCore/AWS services?
It works with Runtime for tool execution, Identity for auth, and Observability for metrics/audit logs. AWS Marketplace partner tools can also be imported automatically.

## Policy

### What is AgentCore policy?
A layer that intercepts every tool call at the Gateway in real time to enforce which tools/data an agent can access, what actions it can take, and under what conditions — enforced outside the agent's own code so it stays consistent even if prompts or agent behavior change. Rules can be authored in natural language (auto-converted to Cedar, AWS's open-source authorization language) or written directly in Cedar.

### What are the key benefits of AgentCore policy?
1. **Keeps agents within bounds** — every tool call is checked against policy before execution.
2. **No added latency** — real-time enforcement at high request volume.
3. **Simplified authoring/governance** — natural-language rule creation lowers the barrier for non-experts while remaining auditable.

### How does natural language policy authoring work?
The system interprets a plain-English rule description, generates candidate policies, validates them against the tool schema, and applies automated checks for issues like overly permissive/restrictive or unsatisfiable conditions — flagging problems before enforcement. It's also available via an MCP server so developers can author/validate policy from their IDE.

### How does policy work with other AgentCore capabilities?
It integrates with Gateway for enforcement, Identity for authentication/authorization, and Observability for audit logging — independent of whatever framework or model the agent uses.

### How does policy work with Amazon Bedrock Guardrails?
Guardrails can be defined within policy to flag threats like prompt injection or sensitive-data exposure; when triggered, policy enforces the defined rule at the gateway layer (outside the agent's own reasoning), so detection can be probabilistic while the final allow/deny enforcement remains deterministic.

## Memory

### What is AgentCore Memory?
A managed memory service supporting both short-term (multi-turn conversation) and long-term (persistent, cross-session) memory, with the ability to share memory across agents. Handles vector embeddings, storage, consolidation, and reflection automatically, while letting developers define custom extraction logic with their own models/prompts.

### What are the key benefits of AgentCore Memory?
1. **No infrastructure to manage** — embeddings, storage, and consolidation are handled automatically.
2. **Enterprise-grade security** — encrypted, namespace-based storage for segmenting memory (by user, project, business unit, etc.) within a VPC.
3. **Deep customization** — choose prebuilt extraction strategies or write custom logic tailored to the use case.

## Code Interpreter

### What is AgentCore Code Interpreter?
A secure sandbox for agents to write and run code, with prebuilt runtimes for multiple languages, large-file support, internet access, and configurable instance types/session settings.

### What are the key benefits of AgentCore Code Interpreter?
1. **Secure execution** — isolated, VPC-supported sandboxes for workflows and data analysis.
2. **Large-scale data handling** — reference S3 files directly for gigabyte-scale processing.
3. **Ease of use** — managed default mode with prebuilt runtimes (JavaScript, TypeScript, Python) and common libraries preinstalled.

## Browser

### What is AgentCore Browser?
A managed, cloud-based browser runtime that lets agents carry out web workflows at scale, with VM-level isolation, federated identity, reduced CAPTCHA friction, live-view/session-replay observability, and automatic scaling.

### What are the key benefits of AgentCore Browser?
1. **Serverless infrastructure** — fully managed, auto-scaling browser access.
2. **Enterprise security** — VM-isolated sandboxes, VPC support, session-level isolation, and automated CAPTCHA handling.
3. **Observability** — real-time visibility and full recorded history of browser sessions for troubleshooting/compliance.

## Identity

### What is AgentCore Identity?
Lets agents securely operate across OAuth-enabled services (Slack, Salesforce, GitHub, etc.), API-key-protected resources, and AWS resources — on a user's behalf or independently — using scoped, identity-aware authorization. Works with existing identity providers (Cognito, Entra ID, Okta) rather than requiring migration, and stores provider credentials/tokens in a secure vault. Supports standard OAuth grants (2LO/3LO) across Runtime and Gateway.

### What are the key benefits of AgentCore Identity?
1. **Secure delegated access** — scoped permissions and identity-aware decisions for agents.
2. **Faster development** — reuse existing identity providers instead of building custom identity infrastructure.
3. **Simplified enterprise auth** — native support for common OAuth services plus custom claims for multi-tenant rule-setting.
4. **Streamlined UX** — the vault and 3LO flow reduce repeated consent prompts for end users.

### How does Identity provide secure access while streamlining UX?
On first consent, Identity stores the user's provider tokens and the agent's OAuth client credentials in its vault; the agent can then retrieve tokens as needed without repeated prompts. Expired tokens are refreshed automatically or trigger a new consent request if needed. API keys are stored and retrieved the same secure way.

## Observability

### What is AgentCore Observability?
A managed monitoring service (built on Amazon CloudWatch) giving visibility into agent execution — traces, session counts, latency, duration, token usage, error rates — with metadata tagging/filtering and OpenTelemetry compatibility for tools like Arize Phoenix, Braintrust, Dynatrace, Datadog, Langfuse, and LangSmith. Supports custom attributes/business metadata on traces.

### What are the benefits of AgentCore Observability?
1. **Quality and trust** — end-to-end visibility into agent reasoning, inputs, outputs, and tool use for debugging and audits.
2. **Faster time to market** — CloudWatch dashboards give a single view of operational health without manual data-stitching.
3. **Flexible tool integration** — OTEL compatibility lets you plug into existing monitoring stacks alongside native CloudWatch support.

## Evaluations

### What is AgentCore Evaluations?
A managed, continuous quality-monitoring service that samples and scores live agent interactions using 13 built-in evaluators (e.g., correctness, helpfulness, relevance) plus custom evaluators for business-specific criteria.

### What are the key benefits of AgentCore Evaluations?
1. **Continuous, real-time quality signal** — ongoing scoring across built-in evaluators surfaces performance patterns from real usage.
2. **No infrastructure to build** — prebuilt evaluators remove the need to build your own LLM-evaluation pipeline.
3. **Custom scoring** — define business-specific evaluators with your own prompts/models.

### What metrics does Evaluations track?
Thirteen built-in evaluators: correctness, faithfulness, helpfulness, response relevance, conciseness, coherence, instruction following, refusal detection, goal success rate, tool selection accuracy, tool parameter accuracy, harmfulness, and stereotyping detection — plus support for custom evaluators.

## Optimization

### What is AgentCore optimization?
Turns production traces into a repeatable improvement loop: surface hidden problems, generate data-grounded fixes, and validate them before shipping — including catching "silent" failures that look fine on dashboards (e.g., an agent claiming to do something it didn't). Works regardless of where the agent runs (AgentCore Runtime, Lambda, EKS, or non-AWS).

### What are the key benefits of AgentCore optimization?
1. **Surfacing hidden problems** — failure, intent, and trajectory insights across many sessions reveal patterns single-trace review would miss, rankable by how widely they affect users; can run as continuous monitoring or a targeted investigation.
2. **Evidence-based fixes** — recommendations analyze traces/evaluation data to suggest concrete changes to prompts/tool descriptions, testable via batch evaluation against a test dataset before deployment.
3. **Validation before shipping** — A/B testing compares agent versions on live traffic to confirm a change actually helps before fully committing to it.

## Registry (Preview)

### What is AWS Agent Registry?
A centralized catalog for discovering, reusing, and governing agents, tools, and agent skills org-wide. Stores structured metadata for each resource (publisher, protocols, capabilities, invocation details), natively supports MCP and A2A, and allows custom schemas. Works across AgentCore, other providers, and on-premises resources.

### What are the key benefits of AWS Agent Registry?
1. **Centralized visibility** — a single source of truth spanning AgentCore, other vendors, and on-prem resources.
2. **Governance controls** — configurable approval workflows, IAM/OAuth-based publish/consume permissions, and CloudTrail audit trails.
3. **Faster discovery** — hybrid keyword + semantic search helps teams find existing tools before building duplicates.

### What's the difference between Registry and Gateway?
Gateway is about execution — turning APIs/Lambda functions into usable tools and connecting to MCP servers at runtime. Registry is about discovery and governance — a broader catalog covering all agents, tools, and skills org-wide. Gateway itself can be listed as a discoverable resource inside Registry.

## Payments (Preview)

### What is AgentCore payments (Preview)?
Lets agents autonomously pay for resources (APIs, MCP servers, web content, other agents) without developers building payment logic from scratch — handling wallet authentication, payment orchestration, spend governance, and observability. At preview, supports stablecoin micropayments via third-party wallets (Coinbase, Stripe) using the x402 protocol, with deterministic per-session spend limits enforced at the infrastructure layer. (AWS notes additional Service Terms apply.)

### What are the key benefits of AgentCore payments?
1. **Managed payment lifecycle** — wallet auth, orchestration, enforced spend limits, and observability, without custom payment infrastructure.
2. **Built-in governance/security** — deterministic spend limits, required end-user authorization before any payment, access controls over who can invoke payment APIs, and no exposure of wallet keys to the agent itself.
3. **Open design** — works with both crypto-native (Coinbase) and traditional (Stripe) rails via a protocol-agnostic architecture (x402 at preview, with more planned).

## Developer Experience

### What is the managed harness in AgentCore?
A preview feature that bundles compute, tooling, memory, identity, and security so a developer can declare an agent's model, tools, and instructions and get a runnable agent in as few as three API calls — with changes handled as config updates rather than code rewrites.

### What is the AgentCore CLI?
A command-line interface for the full agent lifecycle — scaffolding, configuring, deploying, and updating agents — without needing the console. Also exposed via the open-source MCP Server so AI coding assistants can trigger the same workflows from natural-language prompts.

### What is the AgentCore SDK, and how do I access it?
A developer toolkit for building, configuring, and deploying agents with any framework (Strands, LangGraph, CrewAI, custom, etc.), covering agent behavior, short/long-term memory, built-in tools (code interpreter, browser), Gateway connections, observability, and identity/auth. Installed via your AWS account (Python SDK or the AgentCore starter toolkit); uses IAM/AgentCore Identity for inbound auth and standard protocols for outbound/tool auth.

### What is the open-source AgentCore MCP Server, and what does it do?
Bridges natural-language coding workflows (in IDEs like Kiro, or assistants like Claude Code, GitHub Copilot, Q Developer CLI) with AgentCore, translating instructions/existing code into AgentCore-compatible implementations. Installs with a single command and manages AgentCore configuration/dependencies automatically.

## Billing and Compliance

### How am I charged for using AgentCore?
Consumption-based pricing with no upfront commitment or minimum fees. Each service (Runtime, Gateway, Identity, Memory, Observability, Browser, Code Interpreter) is billed independently, so you pay only for what you use. See the AgentCore pricing page for details.

### What is the SLA for AgentCore?
The standard Amazon Bedrock Service Level Agreement applies to AgentCore.

### What security and compliance standards does AgentCore support?
AWS states AgentCore aligns with numerous compliance programs, including BIO, C5, CISPE, CPSTIC, ENS High, FINMA, GNS, GSMA, HITRUST, IRAP, ISMAP, the ISO 27001/27017/27018/27701/22301/20000/9001 family, CSA STAR, MTCS, OSPAR, PCI, Pinakes, PiTuKri, and SOC. It is also HIPAA eligible and is pursuing FedRAMP compliance, with third-party audits ongoing across cycles.