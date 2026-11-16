"""Interview tracks, stakeholder personas and code-review challenges, all mapped
to the AI Engineer job description."""
from __future__ import annotations

TRACKS = {
    "rag": {
        "title": "RAG systems",
        "jd": "Build RAG systems, including data ingestion, retrieval, orchestration, and response generation",
        "focus": "chunking and ingestion of messy enterprise docs (SharePoint, PDFs, ERP exports); embeddings vs keyword vs hybrid retrieval; re-ranking; access control/permission trimming; citations; handling unanswerable questions; freshness and re-indexing; evaluation of retrieval vs generation separately; cost and latency",
        "seed_questions": [
            "Walk me through a RAG system you built end to end. What were the sources and how did you ingest them?",
            "Answers are confidently wrong about 10% of the time. How do you find out whether retrieval or generation is the problem?",
            "How would you make sure an employee never sees content from documents they don't have permission to read?",
        ],
        "rubric": ["Ingestion & chunking choices", "Retrieval design (hybrid, re-ranking)", "Grounding, citations & abstention",
                   "Evaluation approach", "Production concerns (security, freshness, cost)"],
    },
    "agents": {
        "title": "Agents & orchestration",
        "jd": "Develop multi-agent and workflow orchestration solutions that leverage tool calling, memory management, multi-step reasoning and decision-making logic (LangGraph, CrewAI, Semantic Kernel, AutoGen)",
        "focus": "when to use a deterministic workflow vs an autonomous agent; LangGraph state machines, checkpoints, human-in-the-loop interrupts; tool design and descriptions; idempotency of write actions; memory (short-term, summaries, long-term stores); multi-agent patterns (supervisor, handoffs) and their failure modes; guardrails and step limits; prompt injection via tool outputs",
        "seed_questions": [
            "Tell me about an agent you put into production. Why an agent rather than a fixed workflow?",
            "Design an agent that raises purchase orders in our ERP. How do you stop it from creating duplicate or unauthorised POs?",
            "When would you split work across multiple agents, and what goes wrong when you do?",
        ],
        "rubric": ["Workflow vs agent judgement", "Tool design & safety of actions", "State, memory & orchestration",
                   "Failure handling & guardrails", "Framework fluency (LangGraph/SK/etc.)"],
    },
    "evals": {
        "title": "Evaluation & observability",
        "jd": "Implement evaluation frameworks to monitor accuracy, reliability, hallucination rates, user adoption and business impact; build monitoring, testing and observability",
        "focus": "building golden datasets with SMEs; deterministic checks vs LLM-as-judge and judge calibration; hallucination measurement; regression testing in CI; online monitoring, tracing (LangSmith, MLflow, Arize), drift; user feedback and adoption metrics; tying metrics to business impact",
        "seed_questions": [
            "How did you know your last GenAI system was good enough to ship? What exactly did you measure?",
            "How do you measure hallucination rate, and how do you know your LLM judge is trustworthy?",
            "Six weeks after launch usage drops by half. What do you look at?",
        ],
        "rubric": ["Offline eval design", "LLM-as-judge rigour", "Online monitoring & tracing",
                   "Business & adoption metrics", "Turning evals into decisions"],
    },
    "production": {
        "title": "Production engineering & MLOps",
        "jd": "Develop production-ready AI applications, APIs, and integrations; move AI from proof-of-concept to production",
        "focus": "API design for LLM services; latency, streaming, timeouts, retries, rate limits; cost control and caching; model/version management and rollbacks; secrets and identity; CI/CD with eval gates; Python engineering quality; deployment on Azure (Container Apps, Functions, AKS); enterprise integration (SAP, ServiceNow, Databricks, Snowflake, Fabric)",
        "seed_questions": [
            "What changed in your system between the proof-of-concept and the production version?",
            "Your LLM provider has a partial outage and p95 latency triples. What did you build in advance for this?",
            "How do you ship a prompt change safely?",
        ],
        "rubric": ["PoC to production judgement", "Reliability engineering", "Cost & performance",
                   "Security, identity & compliance", "Python & software engineering quality"],
    },
    "ownership": {
        "title": "Ownership & communication (behavioural)",
        "jd": "Ability to clearly explain what was built, why specific architectural decisions were made, and how trust, accuracy and reliability were established; extreme ownership; work with business stakeholders",
        "focus": "STAR-style stories with specifics; architectural decisions and trade-offs; how trust was earned with business users; explaining to non-technical stakeholders; owning failures; moving from idea to measurable business impact; learning new tools quickly",
        "seed_questions": [
            "Tell me about an AI initiative you took from idea to measurable business impact. What was the impact, in numbers?",
            "Describe a time your AI system was wrong in front of a business stakeholder. What did you do?",
            "Explain a key architectural decision you made to someone from Finance.",
        ],
        "rubric": ["Specificity & evidence", "Decision rationale", "Trust & reliability story",
                   "Ownership & accountability", "Communication clarity"],
    },
    "azure": {
        "title": "Microsoft AI stack",
        "jd": "Preferred: Azure OpenAI, Azure AI Foundry, Copilot Studio, Semantic Kernel; vector databases; Databricks, Snowflake or Microsoft Fabric",
        "focus": "Azure AI Foundry projects and model deployments; Azure AI Search (hybrid + semantic ranker, security trimming); Semantic Kernel plugins/agents vs LangGraph; Copilot Studio vs custom build; managed identity, Key Vault, private endpoints; Fabric/Databricks as data sources; cost management",
        "seed_questions": [
            "When would you build on Copilot Studio and when would you build a custom agent?",
            "Design document Q&A over SharePoint on Azure. Which services, and how is security handled?",
            "How would you get Snowflake or Fabric data into an agent safely?",
        ],
        "rubric": ["Service selection judgement", "Security & identity on Azure", "Data platform integration",
                   "Cost awareness", "Hands-on depth"],
    },
    "system_design": {
        "title": "System design case",
        "jd": "Partner with stakeholders to identify automation opportunities; design, develop and deploy AI agents and agentic workflows to solve real business challenges",
        "focus": "a whiteboard-style design of an agentic workflow for an enterprise function: clarify requirements and success metrics, data sources, architecture, human-in-the-loop, evaluation plan, rollout and change management, risks",
        "seed_questions": [
            "Design an AI system that handles invoice exceptions for Accounts Payable at a company processing 40,000 invoices a month. Start by asking me anything you need.",
        ],
        "rubric": ["Requirements & success metrics", "Architecture", "Human-in-the-loop & controls",
                   "Evaluation & rollout plan", "Risk & trade-off reasoning"],
    },
}

PERSONAS = {
    "procurement": {
        "title": "Procurement Manager - PO backlog",
        "function": "Supply Chain",
        "persona": "Marcus Webb, Procurement Manager for the Permian district. Practical, busy, sceptical of 'AI hype' after a failed RPA bot last year. Speaks in operational terms, not tech terms.",
        "opening": "Thanks for coming by. I've got about 20 minutes. My buyers are drowning in purchase orders and someone upstairs said AI could help. Convince me.",
        "hidden_facts": [
            "The team raises about 1,200 POs a month and roughly 35% are routine replenishment of stocked items.",
            "Buyers spend about two days a week on routine replenishment POs.",
            "Requisition-to-PO cycle time is about 4.5 days today; Marcus wants under 1 day for routine items.",
            "The ERP is SAP S/4HANA; there is a read API but PO creation currently goes through a BAPI that only IT can call.",
            "An RPA bot was tried last year and broke whenever the SAP screens changed, so trust is low.",
            "Internal audit requires a clear trail of who or what created and approved every PO.",
            "Approval thresholds are $10k (Category Manager) and $50k (Director) and must not be bypassed.",
            "One supplier (Apex Forge) is on probation and buyers keep accidentally ordering from it.",
        ],
    },
    "ap": {
        "title": "AP Lead - invoice exceptions",
        "function": "Finance",
        "persona": "Sofia Ramirez, Accounts Payable Lead. Detail-oriented, under month-end pressure, worried about controls and auditors.",
        "opening": "Hi. Month-end is in three days so I'll be quick. Invoice exceptions are killing us. What can you do?",
        "hidden_facts": [
            "About 18% of invoices fail three-way match and land in the exception queue.",
            "Most exceptions are unit-of-measure mismatches (each vs box) and freight lines not on the PO.",
            "The team of 6 clerks spends about 60% of their time on exceptions.",
            "Close must finish by business day 5 and exceptions are the bottleneck.",
            "Invoices arrive as PDFs by email and through a supplier portal; matched data lives in SAP.",
            "SOX controls mean nothing can be paid without a human approving out-of-tolerance items.",
            "Sofia's biggest fear is an AI inventing amounts or approving payments by itself.",
            "Success would be cutting exception handling time in half without adding audit findings.",
        ],
    },
    "hr": {
        "title": "HR Ops Manager - policy questions",
        "function": "HR",
        "persona": "Dana Okafor, HR Operations Manager. Employee-experience focused, cautious about sensitive data.",
        "opening": "Hello! My team answers the same questions all day. I'd love a chatbot but I'm nervous about getting it wrong. Where do we start?",
        "hidden_facts": [
            "HR receives about 3,000 tickets a month and about 60% are policy FAQs (PTO, travel, expenses).",
            "Field employees on 14/14 rotation mostly use phones and have patchy connectivity at well sites.",
            "About a quarter of the field workforce prefers Spanish.",
            "Medical leave, harassment and other sensitive topics must always go to a human.",
            "Policies live in SharePoint and are updated every quarter; old versions cause confusion.",
            "A previous vendor chatbot gave a wrong PTO carryover answer and caused grievances.",
            "Dana will measure success by ticket deflection rate and employee satisfaction (CSAT).",
        ],
    },
}

REVIEWS = {
    "rag_endpoint": {
        "title": "Review: a RAG endpoint headed to production",
        "context": "A teammate opened this PR for the HR policy assistant. Review it as you would in a real pod: find the problems and say how you'd fix them.",
        "code": '''import anthropic, functools
client = anthropic.Anthropic(api_key="sk-ant-api03-XXXXXXXXXXXXXXXX")
DOCS = load_all_policy_docs()   # every HR doc, incl. medical-leave case notes

@functools.lru_cache(maxsize=10_000)
def answer(question: str) -> str:
    context = "\\n".join(DOCS)        # 400k tokens
    system = f"You are the HR bot. Policies: {context}. User question: {question}. Always give an answer."
    try:
        r = client.messages.create(model="claude-opus-5-5", max_tokens=200, system=system,
                                   messages=[{"role": "user", "content": question}])
        return r.content[0].text
    except Exception:
        pass
''',
        "issues": [
            "Hard-coded API key committed in source (should come from a secret store / managed identity).",
            "No retrieval: the whole corpus is stuffed into every prompt, which is slow, costly and may exceed context.",
            "Sensitive documents (medical-leave case notes) are included with no access control or permission trimming.",
            "The cache is keyed only on the question text, so answers (and any personal data) are shared across all users and never refreshed when policies change.",
            "The prompt says 'Always give an answer', which forces hallucination instead of abstaining when the docs don't cover it.",
            "User input is interpolated into the system prompt, enabling prompt injection.",
            "No citations or sources returned, so users can't verify answers.",
            "Bare except that swallows errors and returns None, with no logging, retries or user-facing error.",
            "max_tokens=200 may truncate answers and stop_reason isn't checked; r.content[0] assumes the first block is text.",
            "No evaluation, tracing or monitoring hooks.",
        ],
    },
    "agent_loop": {
        "title": "Review: a purchase-order agent loop",
        "context": "This loop runs the procurement agent that can create real POs in SAP. Review it.",
        "code": '''def run(user_msg):
    messages = [{"role": "user", "content": user_msg}]
    while True:
        r = client.messages.create(model=MODEL, max_tokens=4096, tools=TOOLS, messages=messages)
        text = "".join(b.text for b in r.content if b.type == "text")
        messages.append({"role": "assistant", "content": text})
        calls = [b for b in r.content if b.type == "tool_use"]
        if not calls:
            return text
        for c in calls:
            fn = eval(c.name)                      # look up tool function by name
            result = fn(**c.input)
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": c.id, "content": str(result)}]})
''',
        "issues": [
            "No step limit: `while True` can loop forever and burn tokens.",
            "Only the assistant's text is appended, which drops the tool_use blocks so the next request is invalid or loses context.",
            "eval() on a model-chosen name is arbitrary code execution; use an explicit allow-list mapping of tools.",
            "Tool exceptions crash the loop instead of being returned as is_error tool results the model can recover from.",
            "Tool results for parallel calls are sent as separate user messages instead of one message with all results.",
            "Write actions (create PO) have no idempotency, approval gate or human-in-the-loop, so retries can duplicate POs.",
            "Tool inputs are not validated (no strict schemas / business-rule checks) before hitting SAP.",
            "Tool outputs are trusted blindly, with no defence against prompt injection in returned data.",
            "stop_reason isn't checked (max_tokens, refusal, pause_turn).",
            "No tracing or logging of tool calls for audit.",
        ],
    },
    "eval_script": {
        "title": "Review: an evaluation script used for a go/no-go decision",
        "context": "This script produced the '94% accuracy' number in the steering committee deck. Review it.",
        "code": '''QUESTIONS = load_jsonl("golden.jsonl")        # 50 questions written by the dev team
FEW_SHOT = QUESTIONS[:10]                      # used as examples in the production prompt

def judge(q, gold, pred):
    p = f"Question: {q}\\nReference: {gold}\\nAnswer: {pred}\\nIs the answer good? yes/no"
    return "yes" in call_llm(p).lower()

scores = []
for q in QUESTIONS:
    try:
        pred = rag_answer(q["question"])
        scores.append(judge(q["question"], q["answer"], pred))
    except Exception:
        continue
print(f"accuracy = {sum(scores)/len(scores):.0%}")
''',
        "issues": [
            "Test leakage: the first 10 golden questions are also few-shot examples in the production prompt.",
            "The golden set was written by the dev team, not business SMEs, and has only 50 questions with no unanswerable or adversarial cases.",
            "Failures/exceptions are silently skipped, which inflates accuracy (survivorship bias).",
            "The judge prompt is vague ('is the answer good?') and parsed with `'yes' in`, which also matches 'yes' inside 'no, yes...' etc.",
            "The judge isn't calibrated against human labels; there's no agreement measurement.",
            "Only a single aggregate number: no breakdown of groundedness/hallucination, retrieval vs generation, or per-category results.",
            "Single run with no variance or confidence interval; 50 samples gives a wide error bar.",
            "No latency/cost metrics and results aren't stored/versioned for regression comparison.",
        ],
    },
}
