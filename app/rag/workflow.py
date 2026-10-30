import re
import logging
from typing import Literal, Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

from app.core.config import get_settings
from app.rag.state import AgentState, RouteDecision, EvidenceGrade
from app.rag.vectorstore import get_retriever
from app.services.guardrails import redact_pii, guardrails_engine

logger = logging.getLogger(__name__)
settings = get_settings()

_llm = None
_web_search = None


def get_llm():
    """Returns active Chat LLM (OpenAI or Groq) with fallback."""
    global _llm
    if _llm is None:
        if settings.openai_api_key:
            from langchain_openai import ChatOpenAI
            _llm = ChatOpenAI(
                model=settings.openai_model,
                temperature=0,
                api_key=settings.openai_api_key,
            )
        elif settings.groq_api_key:
            try:
                from langchain_groq import ChatGroq
                _llm = ChatGroq(
                    model=settings.groq_model,
                    temperature=0,
                    api_key=settings.groq_api_key
                )
            except ImportError:
                logger.warning("langchain-groq not installed, falling back to simulated engine.")
                _llm = None

        if _llm is None:
            # Resilient internal engine for testing and environments without external keys
            class MockEnterpriseLLM:
                def invoke(self, prompt, **kwargs):
                    prompt_str = str(prompt)
                    class Response:
                        content = ""
                    r = Response()
                    # Router check
                    if "RouteDecision" in prompt_str or "Use kb for" in prompt_str:
                        user_q = ""
                        if "Question:" in prompt_str:
                            user_q = prompt_str.split("Question:")[-1].split("\n")[0].strip().lower()
                        if re.search(r"\b(hello|hi|hey|thanks|thank you)\b", user_q):
                            r.content = '{"route": "direct"}'
                        else:
                            r.content = '{"route": "kb"}'
                        return r
                    # Grader check
                    if "EvidenceGrade" in prompt_str or "grade evidence" in prompt_str.lower():
                        if "vpn" in prompt_str.lower() or "password" in prompt_str.lower() or "mfa" in prompt_str.lower() or "runbook" in prompt_str.lower():
                            r.content = '{"grade": "good"}'
                        else:
                            r.content = '{"grade": "weak"}'
                        return r
                    # Direct check
                    if "Respond briefly and naturally" in prompt_str:
                        r.content = "Hello! I am your NovaRetail Enterprise IT Support Copilot. How can I assist you with VPN, MFA, password reset, or equipment today?"
                        return r
                    # General IT response from KB Context
                    if "Private KB Context:" in prompt_str:
                        r.content = (
                            "Based on NovaRetail enterprise IT documentation:\n\n"
                            "1. **Remote Access & VPN**: Connect using the Palo Alto GlobalProtect VPN client directed to `vpn.novaretail.com`. Authenticate with your corporate credentials and approve the Okta Verify MFA push notification.\n"
                            "2. **Security Compliance**: Never share your password or one-time MFA codes with anyone, including IT support personnel.\n"
                            "3. **Support Escalation**: For unresolved connectivity issues, contact the IT Service Desk at `helpdesk@novaretail.com` or call internal extension **x4357**."
                        )
                        return r
                    r.content = "Based on NovaRetail enterprise documentation: Please follow the standard IT procedures outlined in the company handbook. For remote access, connect via the GlobalProtect VPN client using your corporate SSO and MFA. If issues persist, contact the IT Service Desk."
                    return r

                def with_structured_output(self, schema, **kwargs):
                    class StructuredWrapper:
                        def __init__(self, s):
                            self.schema = s
                        def invoke(self, p):
                            p_str = str(p).lower()
                            if self.schema == RouteDecision:
                                user_q = ""
                                if "question:" in p_str:
                                    user_q = p_str.split("question:")[-1].split("\n")[0].strip()
                                if re.search(r"\b(hello|hi|hey|thanks|thank you)\b", user_q):
                                    return RouteDecision(route="direct")
                                return RouteDecision(route="kb")
                            if self.schema == EvidenceGrade:
                                if any(w in p_str for w in ["vpn", "password", "mfa", "novaretail", "policy"]):
                                    return EvidenceGrade(grade="good")
                                return EvidenceGrade(grade="weak")
                            return None
                    return StructuredWrapper(schema)

            _llm = MockEnterpriseLLM()
    return _llm


def web_search_tool():
    global _web_search
    if _web_search is None:
        if settings.tavily_api_key:
            from langchain_tavily import TavilySearch
            _web_search = TavilySearch(
                tavily_api_key=settings.tavily_api_key,
                max_results=5,
                topic="general",
                include_answer=True,
                include_raw_content=False,
            )
        else:
            class MockTavilySearch:
                def invoke(self, query_dict: dict):
                    q = query_dict.get("query", "")
                    return {
                        "answer": f"Microsoft Service Health Bulletin: Vendor reports resolved incident for Teams connectivity. Ensure client is updated to latest release.",
                        "results": [
                            {
                                "title": "Microsoft 365 Service Status",
                                "url": "https://admin.microsoft.com/servicestatus",
                                "content": "Status active: All core services operating normally. Check local firewall or proxy if connectivity fails."
                            }
                        ]
                    }
            _web_search = MockTavilySearch()
    return _web_search


def add_trace(state: AgentState, message: str) -> List[str]:
    return [*state.get("trace", []), message]


# ========================================================
# 1. INPUT GUARDRAILS (PRESIDIO & NEMO)
# ========================================================

def presidio_input_guard(state: AgentState) -> Dict[str, Any]:
    """Scans user question for PII (emails, phones, SSNs, credentials) and redacts them."""
    raw_question = state["question"]
    anonymized_text, detected_entities = redact_pii(raw_question)
    
    trace_msg = "[Presidio PII Guard] No sensitive PII detected"
    if detected_entities:
        ent_types = ", ".join(sorted({e["entity_type"] for e in detected_entities}))
        trace_msg = f"[Presidio PII Guard] Redacted {len(detected_entities)} entity/entities ({ent_types})"

    return {
        "current_query": anonymized_text,
        "pii_redacted": bool(detected_entities),
        "detected_pii": detected_entities,
        "trace": add_trace(state, trace_msg),
    }


def nemo_input_guard(state: AgentState) -> Dict[str, Any]:
    """Validates the sanitized query against NeMo Guardrails (jailbreak, injection, off-topic)."""
    validation = guardrails_engine.validate_input(state["current_query"])
    if not validation.get("allowed", True):
        return {
            "guardrails_blocked": True,
            "guardrail_reason": validation.get("reason", "Query blocked by enterprise safety rails."),
            "policy_violated": validation.get("policy_violated", "SEC-POL-01"),
            "trace": add_trace(state, f"[NeMo Guardrails] BLOCKED: {validation.get('policy_violated')}"),
        }

    return {
        "guardrails_blocked": False,
        "guardrail_reason": "",
        "policy_violated": "",
        "trace": add_trace(state, "[NeMo Guardrails] Input verified safe (Passed Jailbreak & Scope Rails)"),
    }


def route_after_input_guard(state: AgentState) -> Literal["guardrail_blocked_response", "route_question"]:
    if state.get("guardrails_blocked"):
        return "guardrail_blocked_response"
    return "route_question"


# ========================================================
# 2. ROUTING & RETRIEVAL (HYBRID RAG)
# ========================================================

def route_question(state: AgentState) -> Dict[str, Any]:
    q = state["current_query"]
    # Fast path for common greetings
    if q.strip().lower() in {"hi", "hello", "hey", "good morning", "good evening", "thanks", "thank you"}:
        return {
            "source_used": "direct",
            "trace": add_trace(state, "Router → DIRECT (Greeting/Conversational)"),
        }

    try:
        router = get_llm().with_structured_output(RouteDecision, method="json_mode")
        decision = router.invoke(f"""
You route messages for an enterprise IT support assistant.
Use 'kb' for questions about company IT policies, VPN, password reset, MFA, laptop setup,
software access, security, email, devices, troubleshooting, or technology support.
Use 'direct' only for greetings, thanks, or casual chat that needs no company knowledge.
Question: {q}
Return valid JSON like {{"route":"kb"}}.
""")
        route = decision.route if decision else "kb"
    except Exception as e:
        logger.warning("Router structured output fallback: %s", e)
        route = "kb"

    return {
        "source_used": route,
        "trace": add_trace(state, f"Router → {route.upper()}"),
    }


def route_after_router(state: AgentState) -> Literal["retrieve_kb", "direct_answer"]:
    return "retrieve_kb" if state.get("source_used") == "kb" else "direct_answer"


def retrieve_kb(state: AgentState) -> Dict[str, Any]:
    query = state["current_query"]
    docs = get_retriever().invoke(query)
    mode = "Hybrid RAG (Dense + BM25 RRF)" if settings.enable_hybrid_rag else "Dense Vector"
    return {
        "kb_docs": docs,
        "retrieval_mode": mode,
        "trace": add_trace(state, f"{mode} retrieval → {len(docs)} chunks"),
    }


def grade_kb(state: AgentState) -> Dict[str, Any]:
    context = "\n\n".join(
        f"Source: {d.metadata.get('source', 'unknown')}\n{d.page_content}"
        for d in state["kb_docs"]
    )
    
    # If no documents retrieved, immediately grade weak
    if not state["kb_docs"] or not context.strip():
        return {
            "kb_grade": "weak",
            "trace": add_trace(state, "KB evidence grade → WEAK (No relevant chunks)"),
        }

    try:
        grader = get_llm().with_structured_output(EvidenceGrade, method="json_mode")
        grade = grader.invoke(f"""
You grade evidence for an enterprise IT support assistant.
Question: {state['question']}
Private company KB evidence:
{context}

Return 'good' only if the evidence is sufficient to answer the employee specifically and accurately.
Otherwise return 'weak'.
JSON: {{"grade":"good"}} or {{"grade":"weak"}}.
""")
        grade_str = grade.grade if grade else "weak"
    except Exception as e:
        logger.warning("Grader fallback: %s", e)
        # Heuristic grading: check if key question terms exist in chunks
        q_tokens = set(re.findall(r"\w+", state["question"].lower())) - {"how", "what", "is", "the", "do", "i", "to", "my"}
        ctx_lower = context.lower()
        matches = sum(1 for tok in q_tokens if tok in ctx_lower)
        grade_str = "good" if matches >= max(1, len(q_tokens) // 2) else "weak"

    return {
        "kb_grade": grade_str,
        "trace": add_trace(state, f"KB evidence grade → {grade_str.upper()}"),
    }


def after_kb(state: AgentState) -> Literal["generate_from_kb", "search_web"]:
    return "generate_from_kb" if state.get("kb_grade") == "good" else "search_web"


# ========================================================
# 3. WEB SEARCH FALLBACK & GRADING
# ========================================================

def search_web(state: AgentState) -> Dict[str, Any]:
    result = web_search_tool().invoke({"query": state["current_query"]})
    lines, citations = [], []
    if isinstance(result, dict):
        if result.get("answer"):
            lines.append("Search answer: " + result["answer"])
        for item in result.get("results", []):
            title = item.get("title", "")
            url = item.get("url", "")
            content = item.get("content", "")
            lines.append(f"Title: {title}\nURL: {url}\nContent: {content}")
            citations.append({"title": title or url, "url": url, "type": "web"})
    else:
        lines.append(str(result))

    return {
        "web_results": "\n\n".join(lines),
        "citations": citations,
        "source_used": "web",
        "trace": add_trace(state, "Web fallback → External vendor search"),
    }


def grade_web(state: AgentState) -> Dict[str, Any]:
    if not state.get("web_results", "").strip():
        return {"web_grade": "weak", "trace": add_trace(state, "Web evidence grade → WEAK")}

    try:
        grader = get_llm().with_structured_output(EvidenceGrade, method="json_mode")
        grade = grader.invoke(f"""
Question: {state['question']}
Web evidence:
{state['web_results']}
Return 'good' if the evidence is sufficient and directly relevant; otherwise 'weak'.
JSON: {{"grade":"good"}}
""")
        grade_str = grade.grade if grade else "weak"
    except Exception as e:
        grade_str = "good" if len(state["web_results"]) > 40 else "weak"

    return {
        "web_grade": grade_str,
        "trace": add_trace(state, f"Web evidence grade → {grade_str.upper()}"),
    }


def after_web(state: AgentState) -> Literal["generate_from_web", "rewrite_query", "insufficient"]:
    if state.get("web_grade") == "good":
        return "generate_from_web"
    if state.get("retry_count", 0) < settings.max_retries:
        return "rewrite_query"
    return "insufficient"


def rewrite_query(state: AgentState) -> Dict[str, Any]:
    try:
        resp = get_llm().invoke(f"""
Rewrite this IT support question for better enterprise knowledge retrieval.
Preserve intent, add useful technical keywords, do not answer, return only the single rewritten query.
Question: {state['question']}
""")
        rewritten = resp.content.strip() if hasattr(resp, "content") else str(resp).strip()
    except Exception:
        rewritten = f"{state['question']} enterprise corporate IT support policy"

    return {
        "current_query": rewritten,
        "retry_count": state["retry_count"] + 1,
        "trace": add_trace(state, f"Query rewrite → {rewritten}"),
    }


# ========================================================
# 4. GENERATION & OUTPUT GUARDRAILS
# ========================================================

def generate_from_kb(state: AgentState) -> Dict[str, Any]:
    context = "\n\n".join(
        f"[Source: {d.metadata.get('source', 'Private KB')}]\n{d.page_content}"
        for d in state["kb_docs"]
    )
    prompt = f"""You are NovaRetail Enterprise IT Support Copilot. Answer ONLY from the private company KB below.
Be concise, actionable, and safe. If steps are present, format with bullet points.
Never reveal master passwords or invite users to bypass security procedures.
State that this guidance is grounded in NovaRetail private knowledge.

Question: {state['question']}

Private KB Context:
{context}
"""
    try:
        resp = get_llm().invoke(prompt)
        raw_answer = resp.content if hasattr(resp, "content") else str(resp)
    except Exception as exc:
        raw_answer = "According to NovaRetail IT documentation, please consult the official service desk runbook or standard IT policy."

    citations = []
    seen = set()
    for d in state["kb_docs"]:
        src = d.metadata.get("source", "Company IT KB")
        basename = src.replace("\\", "/").split("/")[-1]
        if basename not in seen:
            seen.add(basename)
            score = d.metadata.get("rrf_score", "")
            meta_str = f" (RRF: {score})" if score else ""
            citations.append({
                "title": f"{basename}{meta_str}",
                "url": "",
                "type": "private_kb",
                "retrieval": d.metadata.get("retrieval_mode", "Hybrid")
            })

    return {
        "answer": raw_answer,
        "source_used": "private_kb",
        "citations": citations,
        "trace": add_trace(state, "Answer generation → PRIVATE KB (Grounded)"),
    }


def generate_from_web(state: AgentState) -> Dict[str, Any]:
    prompt = f"""You are NovaRetail Enterprise IT Support Copilot. The private company KB was insufficient.
Answer strictly from the external vendor web evidence below.
Start with: "⚠️ **External Vendor Information**: This guidance is retrieved from external sources and may require IT validation before applying to corporate hardware."

Question: {state['question']}

Web Evidence:
{state['web_results']}
"""
    try:
        resp = get_llm().invoke(prompt)
        raw_answer = resp.content if hasattr(resp, "content") else str(resp)
    except Exception:
        raw_answer = "⚠️ **External Vendor Information**: Please check the external vendor portal for live service status."

    return {
        "answer": raw_answer,
        "source_used": "web_search",
        "trace": add_trace(state, "Answer generation → EXTERNAL VENDOR WEB"),
    }


def output_guardrails(state: AgentState) -> Dict[str, Any]:
    """Runs NeMo and Presidio Output Rails on final generated text."""
    current_answer = state.get("answer", "")
    
    # NeMo Output Rail: Validate credentials and policy safety
    nemo_eval = guardrails_engine.validate_output(current_answer)
    sanitized_answer = nemo_eval.get("sanitized_output", current_answer)

    # Presidio Output Rail: Redact any accidental PII in answer
    final_answer, leaked_pii = redact_pii(sanitized_answer)

    trace_note = "[NeMo & Presidio] Output guardrails passed"
    if leaked_pii:
        trace_note = f"[Presidio] Redacted {len(leaked_pii)} PII token(s) from final answer"

    return {
        "answer": final_answer,
        "trace": add_trace(state, trace_note),
    }


def direct_answer(state: AgentState) -> Dict[str, Any]:
    q = state["question"].lower()
    if any(g in q for g in ["hello", "hi", "hey"]):
        ans = "Hello! I am your NovaRetail Enterprise IT Support Copilot. How can I assist you with VPN, passwords, MFA, or laptop troubleshooting today?"
    else:
        ans = "You're welcome! Let me know if you need any other IT support or policy information."

    return {
        "answer": ans,
        "source_used": "direct",
        "trace": add_trace(state, "Direct response → Conversational (No retrieval needed)"),
    }


def guardrail_blocked_response(state: AgentState) -> Dict[str, Any]:
    reason = state.get("guardrail_reason", "Request blocked by enterprise security guardrails.")
    policy = state.get("policy_violated", "SEC-POL-01")
    blocked_text = (
        f"🛡️ **Enterprise Security Alert ({policy})**\n\n"
        f"{reason}\n\n"
        "If you believe this is in error, please submit an authorized ticket to the Corporate Information Security Team."
    )
    return {
        "answer": blocked_text,
        "source_used": "guardrail_blocked",
        "trace": add_trace(state, f"Terminated → Blocked by NeMo Guardrails ({policy})"),
    }


def insufficient(state: AgentState) -> Dict[str, Any]:
    return {
        "answer": (
            "I could not locate sufficient reliable evidence in either the NovaRetail private knowledge base "
            "or approved external vendor repositories to provide a confident answer. "
            "Please submit a ticket to the IT Service Desk via **helpdesk@novaretail.com** or call internal extension **x4357**."
        ),
        "source_used": "insufficient_evidence",
        "trace": add_trace(state, "Stopped → Insufficient evidence across private KB and web"),
    }


# ========================================================
# 5. LANGGRAPH STATE GRAPH COMPILATION
# ========================================================

def build_graph():
    graph = StateGraph(AgentState)

    # Register Nodes
    graph.add_node("presidio_input_guard", presidio_input_guard)
    graph.add_node("nemo_input_guard", nemo_input_guard)
    graph.add_node("guardrail_blocked_response", guardrail_blocked_response)
    graph.add_node("route_question", route_question)
    graph.add_node("retrieve_kb", retrieve_kb)
    graph.add_node("grade_kb", grade_kb)
    graph.add_node("search_web", search_web)
    graph.add_node("grade_web", grade_web)
    graph.add_node("rewrite_query", rewrite_query)
    graph.add_node("generate_from_kb", generate_from_kb)
    graph.add_node("generate_from_web", generate_from_web)
    graph.add_node("direct_answer", direct_answer)
    graph.add_node("insufficient", insufficient)
    graph.add_node("output_guardrails", output_guardrails)

    # Workflow Edges
    # START -> Presidio PII Guard -> NeMo Safety Guard
    graph.add_edge(START, "presidio_input_guard")
    graph.add_edge("presidio_input_guard", "nemo_input_guard")

    # Conditional after NeMo: Proceed to router OR block immediately
    graph.add_conditional_edges(
        "nemo_input_guard",
        route_after_input_guard,
        {
            "guardrail_blocked_response": "guardrail_blocked_response",
            "route_question": "route_question",
        }
    )

    # Route question -> KB or Direct
    graph.add_conditional_edges(
        "route_question",
        route_after_router,
        {
            "retrieve_kb": "retrieve_kb",
            "direct_answer": "direct_answer",
        }
    )

    # KB retrieval -> Grade
    graph.add_edge("retrieve_kb", "grade_kb")

    # Grade KB -> Generate OR Web search
    graph.add_conditional_edges(
        "grade_kb",
        after_kb,
        {
            "generate_from_kb": "generate_from_kb",
            "search_web": "search_web",
        }
    )

    # Web search -> Grade Web
    graph.add_edge("search_web", "grade_web")

    # Grade Web -> Generate Web OR Rewrite Query OR Insufficient
    graph.add_conditional_edges(
        "grade_web",
        after_web,
        {
            "generate_from_web": "generate_from_web",
            "rewrite_query": "rewrite_query",
            "insufficient": "insufficient",
        }
    )

    # Query Rewrite loops back to KB retrieval
    graph.add_edge("rewrite_query", "retrieve_kb")

    # Output guardrails applied on all generations
    graph.add_edge("generate_from_kb", "output_guardrails")
    graph.add_edge("generate_from_web", "output_guardrails")
    graph.add_edge("direct_answer", "output_guardrails")
    graph.add_edge("insufficient", "output_guardrails")

    # Terminations
    graph.add_edge("output_guardrails", END)
    graph.add_edge("guardrail_blocked_response", END)

    return graph.compile()


agent_graph = build_graph()


def ask(question: str, user_id: str = "usr-employee", username: str = "employee", user_roles: List[str] = None):
    initial: AgentState = {
        "question": question,
        "current_query": question,
        "user_id": user_id,
        "username": username,
        "user_roles": user_roles or ["employee"],
        "pii_redacted": False,
        "detected_pii": [],
        "guardrails_blocked": False,
        "guardrail_reason": "",
        "policy_violated": "",
        "kb_docs": [],
        "web_results": "",
        "kb_grade": "",
        "web_grade": "",
        "retrieval_mode": "Hybrid (Dense + BM25 RRF)",
        "answer": "",
        "source_used": "",
        "retry_count": 0,
        "trace": [],
        "citations": [],
    }
    return agent_graph.invoke(initial)
