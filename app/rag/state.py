from typing import List, Dict, Any, Literal, Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field
from langchain_core.documents import Document


class RouteDecision(BaseModel):
    route: Literal["kb", "direct"] = Field(
        description="kb for IT/support questions, company policies, VPN, passwords; direct for greetings and casual pleasantries."
    )


class EvidenceGrade(BaseModel):
    grade: Literal["good", "weak"] = Field(
        description="good if the retrieved evidence contains sufficient and specific information to answer the user; weak otherwise."
    )


class AgentState(TypedDict):
    # Core User Input & Identity
    question: str
    current_query: str
    user_id: str
    username: str
    user_roles: List[str]

    # Guardrails Telemetry
    pii_redacted: bool
    detected_pii: List[Dict[str, Any]]
    guardrails_blocked: bool
    guardrail_reason: str
    policy_violated: str

    # Retrieval & Evidence
    kb_docs: List[Document]
    web_results: str
    kb_grade: str
    web_grade: str
    retrieval_mode: str

    # Agent Decisions & Output
    answer: str
    source_used: str
    retry_count: int
    trace: List[str]
    citations: List[Dict[str, Any]]
