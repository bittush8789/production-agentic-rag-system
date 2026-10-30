import time
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Header, Depends, Query, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import (
    UserContext,
    get_current_user,
    require_roles,
    create_demo_jwt,
    ROLE_EMPLOYEE,
    ROLE_IT_SUPPORT,
    ROLE_ADMIN,
)
from app.rag.workflow import ask
from app.rag.vectorstore import add_documents
from app.services.ingestion import load_file, chunk_documents, SUPPORTED
from app.services.audit import write_audit, get_recent_audits
from app.services.guardrails import get_presidio_engines, guardrails_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")
settings = get_settings()


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=3000, description="The IT support question to ask the copilot")


class TokenRequest(BaseModel):
    username: str = Field(default="demo.employee")
    role: str = Field(default=ROLE_EMPLOYEE, description="employee, it_support, or admin")
    department: str = Field(default="Retail Operations")


@router.get("/health")
def health():
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "features": {
            "hybrid_rag": settings.enable_hybrid_rag,
            "presidio_guardrails": settings.enable_presidio_guardrails,
            "nemo_guardrails": settings.enable_nemo_guardrails,
            "keycloak_enabled": settings.keycloak_enabled,
            "dev_auth_bypass": settings.dev_auth_bypass,
        }
    }


@router.get("/guardrails/status")
def guardrails_status(user: UserContext = Depends(get_current_user)):
    """Returns the operational status of enterprise guardrails and retrieval subsystems."""
    presidio_ok = False
    try:
        analyzer, anonymizer = get_presidio_engines()
        presidio_ok = analyzer is not None and anonymizer is not None
    except Exception as e:
        logger.warning("Presidio status check error: %s", e)

    return {
        "presidio_pii": {
            "status": "active" if (settings.enable_presidio_guardrails and presidio_ok) else "degraded",
            "enabled": settings.enable_presidio_guardrails,
            "custom_recognizers": ["EMPLOYEE_ID", "INTERNAL_API_KEY", "CREDENTIAL"],
        },
        "nemo_guardrails": {
            "status": "active" if settings.enable_nemo_guardrails else "disabled",
            "enabled": settings.enable_nemo_guardrails,
            "rails": ["input_jailbreak_check", "input_topic_scope", "output_credential_leak", "output_grounding"],
        },
        "keycloak_rbac": {
            "status": "connected" if settings.keycloak_enabled else "active_demo_mode",
            "realm": settings.keycloak_realm,
            "client_id": settings.keycloak_client_id,
            "user_authenticated": user.username,
            "user_roles": user.roles,
        },
        "hybrid_rag": {
            "status": "active" if settings.enable_hybrid_rag else "disabled",
            "dense_weight": settings.dense_weight,
            "bm25_weight": settings.bm25_weight,
            "rrf_k": settings.rrf_k,
        }
    }


@router.post("/auth/token")
def generate_token(req: TokenRequest):
    """
    Developer/Demo endpoint for acquiring signed Keycloak-compatible JWT tokens
    with specific RBAC roles (employee, it_support, admin).
    """
    target_role = req.role.lower().strip()
    if target_role not in {ROLE_EMPLOYEE, ROLE_IT_SUPPORT, ROLE_ADMIN}:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{req.role}'. Must be one of: {ROLE_EMPLOYEE}, {ROLE_IT_SUPPORT}, {ROLE_ADMIN}"
        )

    token = create_demo_jwt(
        username=req.username,
        roles=[target_role],
        email=f"{req.username}@novaretail.com",
        department=req.department
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": req.username,
        "role": target_role,
        "department": req.department,
        "instructions": "Pass this token in the header as 'Authorization: Bearer <token>' to test Keycloak RBAC"
    }


@router.get("/auth/me")
def get_current_user_profile(user: UserContext = Depends(get_current_user)):
    """Returns the decoded profile and verified RBAC permissions of the current requester."""
    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "roles": user.roles,
        "department": user.department,
        "auth_provider": user.auth_provider,
        "is_admin": user.has_role(ROLE_ADMIN),
        "is_it_support": user.has_role(ROLE_IT_SUPPORT),
        "is_employee": user.has_role(ROLE_EMPLOYEE)
    }


@router.post("/chat")
def chat(
    payload: ChatRequest,
    user: UserContext = Depends(require_roles([ROLE_EMPLOYEE]))
):
    """
    Main Enterprise IT Support Copilot Chat endpoint.
    Protected by RBAC: Requires at least ROLE_EMPLOYEE.
    Executes Presidio PII guardrail -> NeMo safety rails -> LangGraph Hybrid RAG -> Output Rails.
    """
    start_time = time.perf_counter()
    try:
        result = ask(
            question=payload.question,
            user_id=user.user_id,
            username=user.username,
            user_roles=user.roles
        )
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        guardrail_status = "PASSED"
        if result.get("guardrails_blocked"):
            guardrail_status = f"BLOCKED_{result.get('policy_violated', 'POLICY')}"
        elif result.get("pii_redacted"):
            guardrail_status = "REDACTED_PII"

        write_audit(
            question=payload.question,
            source_used=result["source_used"],
            trace=result.get("trace", []),
            user_id=user.user_id,
            username=user.username,
            roles=user.roles,
            question_redacted=result.get("current_query", payload.question),
            pii_detected=result.get("detected_pii", []),
            guardrail_status=guardrail_status,
            retrieval_mode=result.get("retrieval_mode", "Hybrid"),
            latency_ms=latency_ms
        )

        return {
            "answer": result["answer"],
            "source_used": result["source_used"],
            "trace": result.get("trace", []),
            "citations": result.get("citations", []),
            "rewritten_query": result.get("current_query", payload.question),
            "pii_redacted": result.get("pii_redacted", False),
            "detected_pii": result.get("detected_pii", []),
            "guardrails_blocked": result.get("guardrails_blocked", False),
            "retrieval_mode": result.get("retrieval_mode", "Hybrid"),
            "latency_ms": latency_ms,
            "user": user.username,
        }

    except Exception as exc:
        logger.error("Chat pipeline execution failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Enterprise Copilot runtime error: {str(exc)}"
        ) from exc


@router.post("/ingest")
async def ingest(
    file: UploadFile = File(...),
    x_admin_key: Optional[str] = Header(default=None),
    user: Optional[UserContext] = Depends(get_current_user)
):
    """
    Ingest new enterprise knowledge base documents.
    Protected by RBAC: Requires ROLE_ADMIN or legacy X-Admin-Key matching ADMIN_API_KEY.
    """
    # Check Admin permission via RBAC or legacy Admin Key
    has_admin_role = user and user.has_role(ROLE_ADMIN)
    has_valid_admin_key = (x_admin_key is not None) and (x_admin_key == settings.admin_api_key)

    if not (has_admin_role or has_valid_admin_key):
        logger.warning("Unauthorized ingestion attempt. User: %s, Key provided: %s", getattr(user, 'username', 'None'), bool(x_admin_key))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RBAC Access Denied: Ingestion requires 'admin' role or valid 'X-Admin-Key'."
        )

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{suffix}'. Supported: {', '.join(sorted(SUPPORTED))}"
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / Path(file.filename).name
    dest.write_bytes(await file.read())

    docs = load_file(dest)
    chunks = chunk_documents(docs)
    ids = add_documents(chunks)

    write_audit(
        question=f"INGEST: {dest.name}",
        source_used="ingestion_pipeline",
        trace=[f"Admin '{getattr(user, 'username', 'API_KEY')}' indexed {len(chunks)} chunks into Hybrid Knowledge Base"],
        user_id=getattr(user, 'user_id', 'usr-admin'),
        username=getattr(user, 'username', 'admin'),
        roles=getattr(user, 'roles', [ROLE_ADMIN]),
        guardrail_status="ADMIN_ACTION"
    )

    return {
        "message": "Document successfully indexed into Hybrid RAG Knowledge Base",
        "file": dest.name,
        "chunks": len(chunks),
        "ids_created": len(ids),
        "retrieval_updated": "Dense + BM25 indices synchronized"
    }


@router.get("/audit")
def view_audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: UserContext = Depends(require_roles([ROLE_IT_SUPPORT, ROLE_ADMIN]))
):
    """
    Enterprise Audit & Compliance Endpoint (SOC 2 / GDPR).
    Restricted to IT Support and Admin personnel.
    """
    records = get_recent_audits(limit=limit, offset=offset)
    return {
        "count": len(records),
        "limit": limit,
        "offset": offset,
        "audits": records,
        "requested_by": user.username,
        "role": user.roles
    }
