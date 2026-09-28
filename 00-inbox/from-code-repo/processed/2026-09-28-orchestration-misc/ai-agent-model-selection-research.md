# AI Agent for Unifolio — Model & Architecture Research

**Status:** Research only — no build decision made yet. This document exists to
inform a future `superpowers:brainstorming` architectural design session, not
to replace one.

**Scope:** Unifolio wants to add an AI agent, surfaced inside the app, that
can (a) answer questions about a user's own portfolio (holdings, NAV,
allocation, XIRR, analytics — all already computed server-side) and (b) help
with general financial decisions/knowledge. This doc surveys every viable
option for the underlying model and the surrounding architecture — commercial
frontier LLMs, open-source/self-hostable models, agent-building tooling, and
the India-specific regulatory constraints that shape what the agent is
allowed to say — with pros/cons for each, so the eventual design decision has
a real base to stand on.

**Research method:** four parallel research passes (commercial LLMs,
open-source models, agent/RAG tooling, India compliance), each using live web
search rather than relying on pretrained knowledge, since this market moves
fast. Current as of **2026-09-08**. All findings below are sourced;
link lists are kept per section.

---

## 1. Executive summary

- **No frontier LLM — commercial or open — is reliably good at financial
  arithmetic.** This is the single most important finding, and it's
  provider-agnostic (see §2.2). It means the model-selection question matters
  less than the architecture decision: **the agent must never compute
  portfolio numbers itself.** All numbers (XIRR, gains, allocation %) must
  come from Unifolio's existing `Decimal`-safe backend services as tool
  results; the LLM only narrates/reasons over already-correct numbers. This
  is true no matter which model you pick.
- **Recommended model tier: Claude Sonnet 5** (escalate to Haiku 4.5 for
  cheap/simple lookups), as the best balance of tool-use ergonomics, cost, and
  fit with Unifolio's existing AWS-first stack (RDS/S3/ECS per the accepted
  ADRs) — available via Bedrock's Mumbai region for closer-to-India hosting.
  Gemini 3.5 Flash / 3.1 Flash-Lite is the strongest alternative if raw cost
  or context-window size matters more than AWS-native fit.
- **Skip agent frameworks entirely** (LangChain, CrewAI, AutoGen, Semantic
  Kernel). A hand-rolled tool-calling loop against your own existing
  Dashboard/Analytics service functions is both the current best-practice
  pattern for a single-agent case and the one that fits Unifolio's
  "monolith, not microservices" non-negotiable without adding a second
  orchestration layer.
- **Skip RAG/vector DB for now.** Portfolio data is structured and already in
  Postgres — that's a tool-calling problem, not a retrieval problem. If a
  financial-literacy knowledge base gets built later, use **pgvector**
  (already-running Postgres, no new infra) rather than a dedicated vector DB.
- **Skip self-hosting open-source models.** At MVP scale, the engineering
  cost of running your own inference stack (vLLM/TGI, GPU ops, ~$3–6K/month
  of engineer time) dwarfs any per-token savings. If cost or data-sovereignty
  ever becomes a real pressure point, the pragmatic middle path is
  **hosted-inference-of-open-weights** (DeepInfra, OpenRouter) as a cheaper
  fallback tier — not as the primary model on day one.
- **Skip finance-tuned open models** (FinGPT, Fin-R1, FinBERT) for the
  conversational agent itself — all are research artifacts, unmaintained,
  and none are trained on Indian mutual-fund/SEBI context. A frontier general
  model with grounding over Unifolio's own data will outperform and
  outmaintain any of them.
- **The regulatory line is the real product constraint, not the tech.** SEBI
  treats *personalized buy/sell/hold recommendations* as investment advice
  requiring RIA registration; showing a user their own data/analytics does
  not. The one verifiable local precedent (Novelty Wealth / NovaAI) chose to
  get RIA-licensed rather than word around it. This needs a product decision
  before the "help make decisions" half of the ask can be built — the
  "know everything about their portfolio" half is safe to build now.

---

## 2. Commercial frontier LLMs

### 2.1 Lineup, context, pricing (Sept 2026)

| Provider / Model | Context | Input $/1M | Output $/1M | Notes |
|---|---|---|---|---|
| Anthropic Claude Opus 5 | 1M | $5.00 | $25.00 | Adaptive thinking, native tool-use, effort control |
| Anthropic Claude Sonnet 5 | 1M | $2.00 | $10.00 | Best cost/capability mid-tier |
| Anthropic Claude Haiku 4.5 | 200K | $1.00 | $5.00 | Cheapest Claude, good for high-volume routing |
| OpenAI GPT-5.6 Sol (promo, thru Nov '26) | — | $4.00 | $20.00 | Current mainstream flagship tier |
| OpenAI GPT-6 Astra (new, Sep 3 '26) | — | $10.00 | $50.00 (+$1/$12.50 cache) | Frontier tier, 2.5x Sol's price |
| OpenAI GPT-5.1 (prior gen, still served) | 400K | $0.63 | $5.00 | Cheapest current OpenAI option |
| Google Gemini 3.1 Pro | 1M (2M ceiling) | $2.00 (≤200K) / $4.00 (>200K) | $12.00 / $18.00 | Largest context in market |
| Google Gemini 3.5 Flash | 1M | $1.50 | $9.00 | Tuned for agentic/coding tasks |
| Google Gemini 3.1 Flash-Lite | 1M | ~$0.25 | ~$1.50 | Budget high-volume tier |
| xAI Grok 4.6 | ≤200K / >200K | $2.00 / $4.00 | $6.00 / $12.00 | $0.50 cached input |
| xAI Grok 4.3 | — | $1.25 | $2.50 | Cheaper Grok tier |
| Mistral Large 3 | — | $0.50 | $1.50 | Cheapest frontier-tier model; EU-based |

### 2.2 Financial reasoning & numeric accuracy — the real risk

This is provider-agnostic: **every current frontier LLM has a documented
arithmetic/hallucination problem on financial data.**

- **FinBen** (35 datasets, 23 tasks): even SOTA models hit only 60–70%
  accuracy on multi-hop, SEC-style financial reasoning.
- **FAITH** benchmark: models score 95.6% on simple financial lookups but
  collapse toward **~0% on multivariate calculations** (e.g., "what's my
  post-tax CAGR after this SIP top-up").
- **FailSafeQA**: finance-domain hallucination rates up to **41%** of
  queries.
- No public benchmark currently ranks Claude/GPT/Gemini/Grok/Mistral
  head-to-head specifically on *personal-portfolio arithmetic* (XIRR,
  allocation drift, tax-lot gains) — this space is thin and mostly generic
  finance-QA, not "your own portfolio's math."

**Practical implication, independent of model choice:** never let the LLM
compute numbers itself. Numbers must come from Unifolio's existing
`Decimal`-safe backend as tool results; the model only narrates over
already-computed, trusted numbers. This is an architecture decision (§4),
not a model-selection one — and it neutralizes most of the risk above.

### 2.3 Data privacy, residency, India relevance

| Provider | India-relevant option | Caveat |
|---|---|---|
| Anthropic (Claude) | Amazon Bedrock Mumbai region (`ap-south-1`) via Global cross-Region inference; Claude Platform on AWS | Inference may route cross-region under "Global" profiles — check per-model regional pinning if strict residency is required |
| OpenAI | Data residency program now includes India (data-at-rest) | **Inference still runs on US infrastructure** even when data-at-rest is pinned to India — a real gap for strict PII rules |
| Google Gemini | Vertex AI multi-region incl. `asia-south1` (Mumbai) for many models | Not uniform across the lineup — confirm per model |
| xAI Grok | Business/Enterprise: no training on data; EU expansion | No confirmed India-specific residency; newest/least mature enterprise compliance tooling |
| Mistral | Native EU data residency (GDPR-first) | No India-specific residency found — EU-only story, weakest fit here |

No frontier provider offers a clean "data never leaves India" story the way
a genuinely self-hosted model could — worth flagging since Unifolio handles
financial PII (holdings, transactions) even without PAN persistence.

### 2.4 Agent-building surface, per provider

- **Claude** — native Tool Runner (SDK-level loop automation for tools you
  define) + optional Managed Agents (hosted sandbox, unnecessary here since
  your data lives in your own DB, not a sandbox filesystem). Best fit for
  "wrap my existing FastAPI endpoints as tools."
- **OpenAI** — Assistants/Agents SDK, robust function calling, widest
  third-party tooling ecosystem, but the frontier tier (Astra) is now the
  most expensive option in this entire table.
- **Gemini** — solid function calling, unmatched context window (useful if
  you ever want full transaction history in-context instead of tool calls),
  natural fit if any part of infra ever lands on GCP (it currently doesn't —
  Unifolio is AWS-first per ADRs).
- **Grok** — function calling exists but least battle-tested for structured
  agentic workflows; thinner ecosystem/tooling.
- **Mistral** — function calling supported, but weakest on both "cheapest
  overall" *and* ecosystem/tooling maturity for a production agent.

### 2.5 Rough monthly cost — illustrative

Assumption: 10K MAU, ~10 questions/session, ~3 sessions/user/month (~300K
questions/month), ~1,500 input + 300 output tokens/question, cached
system/tool-schema content (all of Claude/Gemini/Grok support prompt
caching natively, which materially lowers real-world cost below this table):

| Model | Approx. monthly cost |
|---|---|
| Claude Haiku 4.5 | ~$900 |
| Gemini 3.1 Flash-Lite | ~$250 |
| Mistral Large 3 | ~$360 |
| Claude Sonnet 5 | ~$1,800 |
| Gemini 3.5 Flash | ~$1,485 |
| Grok 4.3 | ~$787 |
| GPT-5.1 | ~$733 |
| Claude Opus 5 | ~$4,500 |
| GPT-5.6 Sol | ~$3,600 |
| GPT-6 Astra / Gemini 3.1 Pro | ~$8,000–9,000 |

### 2.6 Pros/cons summary

| Provider | Pros | Cons |
|---|---|---|
| **Anthropic Claude** | Best tool-use ergonomics for wrapping existing endpoints; mid-tier (Sonnet 5) hits a strong cost/quality point; Bedrock Mumbai region for closer-to-India hosting; AWS-native fits Unifolio's existing stack | No India-specific data residency guarantee stronger than "Mumbai region via Bedrock"; still a foreign-hosted API for DPDP purposes |
| **OpenAI** | Widest agent-tooling ecosystem and community support; India data-at-rest residency program exists | Inference still runs on US infra even with residency program; frontier tier (Astra) is the priciest option surveyed; ties you to a non-AWS-native ecosystem |
| **Google Gemini** | Cheapest at the Flash/Flash-Lite tier; largest context window (useful if avoiding a tool-heavy design); `asia-south1` Mumbai region for some models | Not AWS-native (Unifolio's stack is AWS-first per ADRs); residency varies by model, needs per-model confirmation |
| **xAI Grok** | Competitive mid-tier pricing; enterprise no-training guarantee | Least mature agentic/tooling ecosystem surveyed; no confirmed India residency; newest entrant with least production track record |
| **Mistral** | Cheapest frontier-tier pricing overall; EU data residency (GDPR-first) | No India-specific residency; weakest ecosystem/tooling maturity for production agents among frontier options |

---

## 3. Open-source / self-hostable models

### 3.1 General-purpose open-weight models

| Family | Latest (Sep 2026) | License | Commercial use? | Hosting need | Quality vs. frontier commercial |
|---|---|---|---|---|---|
| Llama (Meta) | Llama 3.3 70B (Llama 4 line exists, weaker adoption) | Meta community license | Yes, but **capped** — free only under 700M MAU, requires attribution | ~140GB VRAM fp16 (2×A100 80GB), or quantized to 1×A100 | Solid generalist, now trails Qwen/DeepSeek/GLM on reasoning/coding rankings |
| Qwen (Alibaba) | Qwen 3.6 / 3.7 | Apache 2.0 | Yes, fully unrestricted | 7B–72B range; 7B runs on one consumer GPU (24GB) | One of the strongest open families overall; good multilingual + tool-use |
| DeepSeek | DeepSeek V4 / V4 Pro / V4 Flash | MIT (V4 line) | Yes, fully unrestricted | V4 Pro is a large MoE — realistically API-hosted, not self-run | Near-frontier reasoning (esp. math/logic); historically thinner on financial-domain nuance and English-market compliance framing |
| GLM (Z.ai/Tsinghua) | GLM-5.1 / 5.2 | MIT | Yes | Comparable scale to DeepSeek | Rivals Claude Opus on coding per current rankings; less proven on financial reasoning specifically |
| Gemma (Google) | Gemma 4 | Apache 2.0 | Yes | Optimized for on-device/small deployment (2B–27B) | Good for lightweight/cheap tasks; not a frontier reasoner |
| Mistral/Mixtral (open releases) | Mistral Medium 3.5 | Apache 2.0 | Yes | Mixtral MoE needs multi-GPU; smaller Mistral models run on one GPU | Reliable mid-tier, strong multilingual, generally behind Qwen/DeepSeek on hard reasoning |

**Licensing note:** Apache 2.0 / MIT models (Qwen, DeepSeek, GLM, Gemma) are
the safe commercial choice — no MAU trap like Llama's community license.

### 3.2 Finance-domain-specific open models — be skeptical

| Project | What it is | Maturity verdict |
|---|---|---|
| **FinGPT** (AI4Finance) | LoRA fine-tunes of Llama2-7B/13B, ChatGLM2-6B for sentiment analysis on news/tweets | Research-stage, narrow (sentiment classification only), base models 2 generations stale. **Not production-viable for a user-facing agent.** |
| **FinBERT** | BERT further-pretrained on financial text | Encoder-only — good for sentiment/classification pipelines, **cannot hold a conversation or reason**. Useful only as a component, not the agent itself. |
| **Fin-R1** (SUFE-AIFLM-Lab) | Qwen2.5-7B fine-tuned (SFT+RL) for financial reasoning, SOTA on financial benchmarks at 7B scale, published technical report | Most credible of the group, but Chinese-market-benchmark-trained (accounting/reasoning tasks framed for Chinese financial exams/data), **unvalidated for Indian MF/SEBI context**, no visible production deployment track record. |
| Open-FinLLMs, FinMA, FinRobot, FinTeamExperts | Various 2024–2025 academic Llama-3-based finance fine-tunes/agent frameworks | All academic-paper-stage, no evidence of production hardening or maintenance cadence. |
| BloombergGPT | Context only | Proprietary — not available to you at all. |

**Bottom line:** every finance-specific open model is a research artifact,
not a maintained product, and none are trained on Indian mutual-fund/SEBI
data. A frontier general model with your own grounding/retrieval over
portfolio + India-specific financial content will outperform and outmaintain
any of these — using one in production means inheriting unmaintained weights
with no vendor behind them, a real risk for anything advice-adjacent.

### 3.3 Self-hosting infrastructure

| Approach | Pros | Cons |
|---|---|---|
| **Ollama** | Trivial local setup, good for prototyping | Not built for production multi-user serving/throughput |
| **vLLM** | Best throughput (continuous batching, PagedAttention); the production standard | You own the deploy, scaling, monitoring, upgrades |
| **TGI** (Hugging Face) | Solid alternative to vLLM, good HF ecosystem integration | Same operational burden as vLLM |

**Cost reality (2026):** RunPod on-demand — H100 ≈ $2.89/hr, A100 ≈
$1.39/hr, RTX 4090 ≈ $0.69/hr, billed per-second. Serverless/on-demand beats
an always-on pod below ~51–60% utilization; above that a standing GPU is
cheaper. Either way, **budget 20–30% of a senior engineer's time
(~$3,000–6,000/month) just to keep a self-hosted stack production-safe** —
quantization, batching tuning, failover, upgrades. That ongoing engineering
cost is the real cost, not the GPU sticker price.

**Verdict: not worth it at MVP scale.** Self-hosting only pays off at very
high sustained volume (100M+ tokens/day) or hard data-residency
requirements Unifolio doesn't currently have.

### 3.4 Hosted-inference-of-open-weights — the realistic middle path

| Provider | Positioning | Notable pricing (per 1M tokens, 2026) |
|---|---|---|
| **DeepInfra** | Widest catalog (Kimi K2, Qwen3.5, GLM-5, DeepSeek V4, gpt-oss-120B), consistently cheapest | Llama 3.3 70B: $0.10 in / $0.32 out; DeepSeek V4 Pro: $1.30 / $2.60 |
| **Together AI** | Also supports on-platform fine-tuning | Llama 3.3 70B: $1.04 blended; DeepSeek V4 Pro: $2.10 |
| **Fireworks AI** | Fine-tuning + inference, enterprise-leaning | DeepSeek V4 Pro: $1.74 |
| **Groq** | Custom LPU hardware, fastest tokens/sec, small curated model list | gpt-oss-120B: $0.26 blended |
| **OpenRouter** | Meta-router across providers, one API, one bill | Routes to cheapest/available backend automatically |

This is the realistic way to use open-weights without owning infra — zero
ops burden, pay-per-token like a commercial API, and model-swappable
(DeepSeek ↔ Qwen ↔ GLM) without re-architecting.

### 3.5 Pros/cons summary — open-source path overall

| Approach | Pros | Cons |
|---|---|---|
| Self-host (vLLM/TGI) | Full data control, no per-token vendor cost at high volume, no external data transfer | $3–6K/month of engineering time, GPU capex/opex, you own uptime/scaling/security — wrong shape for an MVP team |
| Hosted-inference-of-open-weights (DeepInfra/OpenRouter) | Cheapest tokens of any path surveyed, zero ops burden, easy model swapping | Still a third-party API (same data-transfer profile as commercial LLMs); model quality/support less predictable than a frontier vendor; no finance-tuned option worth using anyway |
| Finance-tuned open models (FinGPT/Fin-R1/FinBERT) | Free, inspectable weights; Fin-R1 has genuine reasoning benchmarks | Unmaintained, no vendor accountability, not trained for Indian context, encoder-only options (FinBERT) can't converse at all |

---

## 4. Agent-building architecture

### 4.1 Frameworks — recommendation: use none

| Framework | What it's for | 2026 maturity/sentiment | Fit for Unifolio |
|---|---|---|---|
| LangChain / LangGraph | General LLM app framework + graph control flow + LangSmith observability | Largest ecosystem, but persistent mainstream criticism that its abstractions "get in the way" once projects grow past prototype scale | Overkill — buys observability/integrations Unifolio doesn't need for one agent hitting its own REST endpoints |
| LlamaIndex | RAG/data-indexing framework, now also agents | Strong for document-heavy retrieval pipelines | Not a fit — no unstructured corpus to index (see §4.2) |
| CrewAI | Multi-agent "crew" role-play orchestration | Positioned for multi-agent collaboration | Wrong shape — Unifolio needs one agent with tools, not a crew |
| AutoGen / AG2 (Microsoft) | Multi-agent conversation framework | **Now in maintenance mode** — merged into the unified "Microsoft Agent Framework" (GA targeted Q1 2026) | Avoid — mid-consolidation framework is a bad MVP bet |
| Semantic Kernel | Microsoft's .NET/Python/Java orchestration + planning SDK | Being absorbed into the same consolidation as AutoGen | Same caution; also a foreign ecosystem for a Python/FastAPI shop |
| Haystack (deepset) | RAG-first pipeline framework | Mature for retrieval pipelines specifically | Solves a problem Unifolio mostly doesn't have yet |
| OpenAI Agents SDK / Swarm | OpenAI's lightweight agent-loop libraries | Swarm praised as "barely a framework to learn" | Reasonable pattern to imitate; ties you to OpenAI if used directly |
| Anthropic Tool Runner + Claude Agent SDK | Tool Runner = thin loop-automation over the Messages API for tools you define; Agent SDK = full Claude-Code-style harness | Both "harness-only" (you host/deploy) | **Best fit if committing to Claude** — Tool Runner is close to "no framework, plus a loop helper," with per-turn hooks (approval, logging, retries) as a bonus over hand-rolling |
| SmolAgents (Hugging Face) | Lightweight code-execution-focused agent lib | Simpler than CrewAI | Wrong shape — code execution isn't the core need |
| **No framework** | Hand-rolled `while stop_reason == "tool_use"` loop | Explicitly validated 2026 pattern: "call the LLM API, pass tool results back, handle state in your own DB" is the emerging consensus for single/simple-multi-agent cases | **Best overall fit** — full control, zero new dependency risk, fits the TDD-always non-negotiable directly |

**Recommendation, validated not assumed:** a monolith FastAPI backend with
four logical services and an MVP-sized team gains nothing from
LangChain/CrewAI/AutoGen's orchestration machinery, and takes on real cost
(extra dependency surface, abstraction debugging, betting on a framework
mid-consolidation for the Microsoft options). A hand-rolled tool-calling
loop — or a provider's thin tool-runner helper if committing to that
provider's SDK — over existing endpoints is the state-of-the-art pattern for
2026 *and* the one that avoids adding a second orchestration layer next to
FastAPI.

### 4.2 Grounding: RAG vs. direct tool-calling

Portfolio numbers (holdings, NAV, XIRR, allocation) are **already
structured and already live in Postgres** — this is not a RAG problem.
Vector search over embedded documents finds *semantically relevant
unstructured text*; it does not return an exact `Decimal` field. The correct
pattern is **function/tool calling**: define tools like `get_holdings`,
`get_analytics_summary`, `get_xirr` that call existing service-layer
functions directly (in-process, not even over HTTP) and return structured
JSON; the agent reasons over that JSON.

**Numeric hallucination is a real risk even with tool-calling** — models can
fabricate numbers *after* correctly retrieving the right data, or bypass
tool calls entirely and compute from parametric memory (one cited research
case returned a value 33× off from the tool-verified figure). Mitigations
that map directly onto Unifolio's existing conventions:

- **Never let the agent do arithmetic in free text** — any derived number
  must come from a tool call, mirroring the existing `Decimal`-never-`float`
  non-negotiable extended into the agent layer.
- **Force citation to source fields** — require the agent to reference
  which tool result a number came from, making silent fabrication
  structurally harder to slip past review.
- **Constrain the tool surface tightly** — only expose read-only,
  already-audited endpoints (reuse Dashboard/Analytics service functions);
  never give the agent a generic "run SQL" tool against portfolio data.
- **Log every tool call + result pair** for post-hoc audit, given
  financial-advice-adjacent stakes.

### 4.3 Vector DB — only relevant for a future knowledge-base feature

| Option | Verdict for Unifolio |
|---|---|
| **pgvector** | Correct first choice if this is ever needed. Production-proven at real scale (Supabase, Neon, Instacart); multiple 2026 case studies show teams migrating *away from* dedicated vector DBs back to Postgres/pgvector for exactly this profile (one app, moderate corpus). Zero new infra — reuses existing RDS Postgres, one extension. Ceiling ~50M vectors, irrelevant for a hand-authored financial-literacy KB. |
| Pinecone / Weaviate / Qdrant | Only justified past ~5M+ vectors or managed multi-tenant vector infra at scale — none of which applies here. New paid service, new operational dependency, no present benefit. |
| Chroma | Prototyping-only per current consensus (no production multi-tenant/replication story) — skip even for a proof of concept since pgvector is equally easy to stand up and is what you'd actually ship. |

**Recommendation:** don't build a knowledge-base/RAG feature now — there's
no unstructured content to retrieve over yet. If one is added later (e.g., a
"what is TER" glossary, a tax-rule explainer), reach for pgvector directly.

### 4.4 Guardrails / output-safety tooling

| Tool | Approach | Fit |
|---|---|---|
| **Guardrails AI** | Syntactic/structural output validation (Pydantic-style schemas, the RAIL spec) | Lightweight way to enforce "every numeric claim must be schema-validated against a cited tool-result field" — complements the tool-calling design in §4.2 directly |
| **NeMo Guardrails** | Colang-based conversational state-machine / topical rails | Heavier, dialogue-flow-oriented; likely overkill for an MVP, but the right category if a hard rail is needed (e.g., "never phrase output as a buy/sell recommendation") |
| Simple prompt/output patterns (no library) | System-prompt constraints + a lightweight regex/keyword or LLM-judge check before returning a response | Likely sufficient at launch given MVP scope — a dedicated guardrails library is a reasonable v2 addition, not a v1 requirement |

**Cross-industry regulatory signal worth flagging:** 2026 US interagency
guidance (Fed/FDIC/OCC) has explicitly extended model-risk-management
expectations to generative/agentic systems in financial services. That's a
US framework, not SEBI, but it's a signal that "guardrails" is increasingly
treated as a compliance requirement rather than an engineering nicety —
worth a compliance-specific look before shipping investment-adjacent
language, independent of which library (if any) is chosen.

---

## 5. India regulatory landscape

*Not legal advice. Confidence level flagged per point — get counsel review
before shipping anything advice-adjacent.*

### 5.1 SEBI Investment Adviser (IA) Regulations & AI

**Confirmed:**
- SEBI issued a **2025 consultation paper** on AI/ML use in securities
  markets (advisory, risk management, client identification), built around
  governance, human oversight, and vendor-agreement principles. Comment
  period closed July 2025.
- SEBI's stated position (via legal commentary): **"using AI does not
  reduce responsibility, it increases it."** Anyone giving trading/
  investment recommendations — AI-assisted or not — needs to be a
  SEBI-registered Investment Adviser (RIA) or Research Analyst (RA).
- The emerging industry-lawyer-described compliance pattern is
  **"human-in-the-loop"**: AI can accelerate research, but a named,
  registered human must validate/sign off before anything resembling a
  personalized recommendation reaches a user.
- **The core, well-established legal distinction (pre-dates AI):** IA
  registration is triggered by *personalized* advice — "should **you**
  buy/sell/hold X, given your profile." Showing a user their own portfolio
  composition, performance, XIRR, category exposure, or generic educational
  content ("what is expense ratio," "how SIPs work") is **not** advice and
  needs no license. The line is crossed at a personalized buy/sell/hold
  recommendation tied to that specific user's situation.
- **Genuinely unclear, not yet settled:** whether an LLM chatbot answering
  "should I switch this fund?" with reasoning grounded in the user's own
  data, phrased as "here's what the data shows" rather than "I recommend,"
  counts as advice. Legal academic commentary (NLS Forum) explicitly calls
  this a **"definitional gap"** in current SEBI regulation. Treat as a real
  open risk, not a solved problem.

### 5.2 RBI data localization

**Confirmed:** RBI's 2018 data localization circular applies specifically to
**payment system data** (customer/payment/transaction data flowing through
authorized Payment System Operators) — it does not, on its text, generally
cover portfolio/holdings/NAV data in a mutual-fund tracking app's database.

**Uncertain / practical risk:** Unifolio isn't a payment system operator, so
this circular likely doesn't directly bind it. But sending any Indian user's
financial data to a US-hosted LLM API raises the same *class* of concern RBI
has repeatedly signaled it cares about (data sovereignty). **Recommendation:
get this specific question — does RBI localization reach non-payment
financial/portfolio data sent to a foreign LLM API — reviewed by counsel
before shipping**, rather than assuming either extreme.

### 5.3 DPDP Act 2023

**Confirmed, more directly load-bearing than RBI here:**
- No AI-specific chapter — DPDP reaches AI through three existing levers:
  **consent**, **data accuracy**, and (for Significant Data Fiduciaries
  only) an algorithmic-due-diligence duty.
- **Consent is the primary lawful basis** (stricter than GDPR) — must be
  free, specific, informed, unconditional, unambiguous, with clear
  affirmative action, in plain language. **Sending a user's portfolio data
  to a third-party LLM API is a "processing" event requiring its own clear
  consent notice** — bundling it into a generic ToS is legally thin.
- **Automated Decision-Making:** individuals should not be subject to
  decisions based *solely* on automated processing without meaningful human
  oversight — reinforces the same human-in-the-loop pattern SEBI points to,
  relevant if the agent ever suggests actions rather than just answering
  questions.
- Financial-sector data carries **compounding regulatory density** (RBI
  localization where applicable + SEBI CSCRF + DPDP + CERT-In's 6-hour
  breach reporting) — a cross-cutting theme, not unique to this feature.

### 5.4 How competitors position their AI assistant

- **Novelty Wealth's "NovaAI"** (the "NOV" competitor in Unifolio's own
  competitive matrix) is the clearest data point: Novelty Wealth is
  **SEBI-registered as an RIA (INA000019415)**, fee-only/zero-commission,
  and NovaAI is explicitly framed as giving "real-time insights on portfolio
  performance, risk tracking, asset concentration, tax optimization" —
  **they hold the license and build the AI feature inside a licensed
  advisory wrapper**, not as a way to dodge licensing.
- The competitor labeled "FL" in the matrix could not be confirmed as a
  specific named company from this research — worth re-confirming which
  company "FL" refers to in the competitive-matrix source data before
  citing it further.
- **Takeaway:** the one verifiable precedent in this market went the
  "get licensed, then build the AI feature" route, not "stay unlicensed by
  careful wording" — worth weighing against the lighter-touch educational
  framing below as a product decision, not a purely technical one.

### 5.5 General best-practice pattern (cross-industry)

Fintech products that offer "AI insights" without RIA licensing
consistently use some combination of:
- **Educational framing**, with an explicit disclaimer on AI-generated
  content ("for educational purposes only, not investment advice by
  [Company]") — Univest's RA disclaimer is a concrete in-market example.
- **Show the data, not a verdict** — "your equity allocation is 72% vs. your
  stated moderate-risk profile" rather than "you should sell X."
- **No personalized buy/sell/hold output tied to a specific security and
  specific user profile** — the single brightest legal line under current
  SEBI practice.
- **Human-in-the-loop for anything advisory-shaped**, per SEBI's emerging
  AI framework.
- **Explicit, separate consent** for the specific act of sending portfolio
  data to a third-party AI processor, per DPDP.

---

## 6. Decision matrix

| Layer | Recommendation | Why | Confidence |
|---|---|---|---|
| Model | Claude Sonnet 5 primary, Haiku 4.5 for cheap lookups | Best tool-use ergonomics + cost fit + AWS-native (Bedrock Mumbai) alignment with existing stack | High — no benchmark shows a competitor solving the numeric-reasoning problem better, so cost/fit dominates |
| Alternative model | Gemini 3.5 Flash / 3.1 Flash-Lite | Cheapest at scale, largest context, if AWS-native fit matters less than raw cost | Medium |
| Architecture | Direct tool-calling against existing service functions, no framework | Matches monolith non-negotiable, avoids new dependency risk, is the validated 2026 pattern for single-agent cases | High |
| Numeric safety | Agent never computes; all numbers come from existing `Decimal`-safe services as tool results | Neutralizes the one universal weakness of every LLM surveyed | High — should be treated as non-negotiable, same tier as the existing Decimal rule |
| RAG/vector DB | None now; pgvector if/when a knowledge-base feature is scoped | No unstructured corpus exists yet; portfolio data is a tool-calling problem | High |
| Open-source models | Skip for v1; DeepInfra/OpenRouter hosted-inference as a future cost-fallback tier only | Self-hosting ops cost dwarfs savings at MVP scale; no finance-tuned open model is production-credible | High |
| Guardrails | Simple schema/prompt-level checks at v1; reconsider Guardrails AI as tool-result-citation gets stricter | MVP scope doesn't yet justify a dedicated library | Medium |
| Regulatory posture | Product decision required before shipping anything beyond portfolio-data narration | "Show data" is safe now; "help decide" range needs an explicit RIA-or-educational-framing call | This is the one item that blocks scope, not implementation |

---

## 7. Open questions for the user (product decisions, not technical ones)

1. **Scope of "help make decisions."** Does the agent stay in "explain your
   own data" territory (safe, no license needed), or does it extend into
   phrased suggestions ("consider rebalancing," "this fund underperforms its
   category")? The SEBI definitional gap (§5.1) means the second option
   carries real, currently-unsettled regulatory risk without either an RIA
   license or a carefully counsel-reviewed educational-framing approach.
2. **Data residency posture.** Is routing Indian users' portfolio data
   through a US-hosted LLM API (even via a Mumbai inference region)
   acceptable, or does this need a formal legal sign-off first given DPDP's
   consent requirements and the RBI-adjacent uncertainty (§5.2–5.3)?
3. **Budget ceiling** for the model layer, to pick a concrete default tier
   from §2.5 rather than leaving it open-ended.

---

## Sources

**Commercial LLMs:**
- [OpenAI API Pricing (2026)](https://www.morphllm.com/openai-api-pricing)
- [GPT-6 Astra pricing](https://www.cloudzero.com/blog/gpt-6-pricing/)
- [Google Gemini 3 pricing 2026](https://www.eesel.ai/blog/google-gemini-3-pricing)
- [Grok API Pricing (Sep 2026)](https://mem0.ai/blog/xai-grok-api-pricing)
- [Mistral API Pricing In 2026](https://www.cloudzero.com/blog/mistral-api-pricing/)
- [FinReflectKG - HalluBench](https://arxiv.org/html/2603.20252v1)
- [FinVerBench](https://arxiv.org/pdf/2605.29586)
- [FinBen: A Holistic Financial Benchmark](https://proceedings.neurips.cc/paper_files/paper/2024/file/adb1d9fa8be4576d28703b396b82ba1b-Paper-Datasets_and_Benchmarks_Track.pdf)
- [What AWS Regions are Claude models available in Amazon Bedrock?](https://support.claude.com/en/articles/10280791-what-aws-regions-are-claude-models-available-in-amazon-bedrock)
- [Access Anthropic Claude models in India on Amazon Bedrock](https://aws-news.com/article/2026-03-09-access-anthropic-claude-models-in-india-on-amazon-bedrock-with-global-cross-region-inference)
- [Clarification on India-Only Data Residency for Azure OpenAI](https://learn.microsoft.com/en-in/answers/questions/5664854/clarification-on-india-only-data-residency-for-azu)
- [Expanding data residency access to business customers worldwide | OpenAI](https://openai.com/index/expanding-data-residency-access-to-business-customers-worldwide/)

**Open-source models:**
- [Best Open-Source LLMs 2026 | Qwen, GLM, DeepSeek & Llama Compared](https://www.buildfastwithai.com/blogs/collection/open-source-llms)
- [Open Source LLM Comparison Table (2026) | ComputingForGeeks](https://computingforgeeks.com/open-source-llm-comparison/)
- [Open-Source LLMs Landscape 2026: Qwen, Llama, DeepSeek, Kimi](https://codersera.com/blog/open-source-llms-landscape-2026/)
- [GitHub - AI4Finance-Foundation/FinGPT](https://github.com/AI4Finance-Foundation/FinGPT)
- [FinGPT: Open-Source Financial Large Language Models](https://ai4finance.org/research/fingpt-open-source-finllm.html)
- [Fin-R1 GitHub - SUFE-AIFLM-Lab](https://github.com/sufe-aiflm-lab/fin-r1)
- [Fin-R1 paper (arXiv 2503.16252)](https://arxiv.org/abs/2503.16252)
- [Top Inference API Providers for Open-Source Models in 2026 - Novita](https://blogs.novita.ai/inference-api-providers-for-open-source-models/)
- [RunPod Pricing in 2026: What GPU Cloud Actually Costs | Flexprice](https://flexprice.io/blog/runprod-pricing-guide-with-gpu-costs)
- [Self-Hosting an LLM: Options, Costs & GPU Requirements 2026](https://khimananda.com/blog/self-hosting-an-llm-options-costs-and-gpu-requirements)
- [BloombergGPT and the Limits of Domain-Specific LLMs in Finance](https://beancount.io/bean-labs/research-logs/2026/05/05/bloomberggpt-large-language-model-finance)

**Agent tooling / RAG / guardrails:** (general web research on framework
maturity, pgvector vs. vector-DB migration case studies, and 2026 US
interagency AI-model-risk guidance — see the fork transcript for exact URLs
if needed; primary claims cross-checked against Anthropic's own current
Tool Runner / Managed Agents documentation.)

**India compliance:**
- [SEBI's New Digital Compliance Rules 2026 — Mondaq](https://www.mondaq.com/india/securities/1759228/sebis-new-digital-compliance-rules-what-investment-advisers-must-know-in-2026)
- [Algorithmic Investment Advice and the Definitional Gap in SEBI's Regulation of AI — NLS Forum](https://forum.nls.ac.in/ijlt-blog-post/algorithmic-investment-advice-and-the-definitional-gap-in-sebis-regulation-of-ai-powered-trading-part-ii/)
- [SEBI's Consultation Paper on AI/ML Guidelines — Lexology](https://www.lexology.com/library/detail.aspx?g=1ad14350-2973-4596-8e27-b4458dc6c039)
- [SEBI's AI/ML Framework — Mondaq](https://www.mondaq.com/india/securities/1701020/sebis-aiml-framework-balancing-innovation-compliance-and-market-integrity)
- [RBI's Data Localization Rule — Appknox](https://www.appknox.com/blog/data-localization-rule-by-rbi)
- [AI and Machine Learning Under DPDPA — DPDPA.com](https://www.dpdpa.com/blogs/ai_machine_learning_dpdpa_compliance_guide.html)
- [India's DPDP Act: What It Says About AI — Multigrid](https://multigrid.ai/learn/india-dpdp-act-ai-provisions)
- [Indian Wealth Platform Novelty Wealth Raises $1.4M — Hubbis](https://hubbis.com/news/indian-wealth-platform-novelty-wealth-raises-usd1-4-million-seed-round-to-expand-ai-driven-advisory)
- [Novelty Wealth: AI for Finance — Google Play](https://play.google.com/store/apps/details?id=in.noveltywealth.app&hl=en_IN)
- [SEBI Investment Adviser services scope — Univest](https://univest.in/blogs/sebi-registered-investment-adviser-services)
