# Architecture Statement of Work (SOW)
## Project: Enterprise IT Support Agentic RAG Copilot

---

**Document Reference**: SOW-FDE-NOVARETAIL-2026-001  
**Customer**: NovaRetail Inc.  
**Author**: Lead Forward Deployed Engineer (FDE)  
**Effective Date**: October 30, 2026  
**Status**: APPROVED & EXECUTED  

---

## 1. Project Background & Business Intent

NovaRetail Inc. operates 45 retail stores and corporate offices supporting 3,000 employees. The internal IT Service Desk manages over 14,000 inquiries monthly, of which **42% (5,880 tickets)** are repetitive Tier-1 questions regarding:
1. Virtual Private Network (VPN) setup and remote connectivity.
2. Single Sign-On (SSO) and Multi-Factor Authentication (MFA) registration.
3. Password reset policies and device encryption standards.
4. Approved software catalog and hardware procurement.

**Business Objective**: Build, validate, and deploy a secure **Enterprise IT Support Agentic RAG Copilot** capable of resolving Tier-1 questions autonomously using private corporate runbooks, while guarding against prompt injection, preventing PII leaks, enforcing Keycloak role boundaries, and handling cloud vendor outages transparently.

---

## 2. In-Scope vs. Out-of-Scope

### 2.1 In-Scope Deliverables
* **Hybrid RAG Retrieval Engine**: Dense Vector Search (Pinecone Serverless) + Sparse BM25 Keyword Search combined via Reciprocal Rank Fusion (RRF).
* **Multi-Format Ingestion Pipeline**: Ingestion support for PDF, Markdown, Plain Text, and DOCX runbooks with recursive text chunking.
* **Microsoft Presidio PII Shield**: Pre-LLM interceptor masking emails, phone numbers, SSNs, and custom enterprise employee IDs (`EMP-xxxxx`).
* **NVIDIA NeMo Guardrails Engine**: Input rails for jailbreak / prompt injection defense, scope enforcement, and output grounding verification.
* **Keycloak Identity & RBAC**: OIDC JWT RS256 token verification with granular role enforcement (`ROLE_EMPLOYEE`, `ROLE_IT_SUPPORT`, `ROLE_ADMIN`).
* **SOC 2 / GDPR Audit Ledger**: Immutable SQLite tracking recording query history, masked versions, guardrail outcomes, and latency.
* **Production Docker Container**: Multi-worker, non-root user (UID 10001), CIS benchmark compliant.

### 2.2 Out-of-Scope
* Modifying third-party identity provider directories (Keycloak user provisioning remains customer responsibility).
* Automatic ticket resolution in customer's ITSM tool (read/write connector to ServiceNow/Jira is planned for Phase 2).
* Hardware procurement for local edge appliances.

---

## 3. Workstream Deliverables & Milestones

| Workstream ID | Deliverable Title | Technical Specification | Acceptance Criterion |
|---|---|---|---|
| **WS-1** | Knowledge Ingestion Pipeline | Multi-format loader (`pypdf`, `python-docx`, `TextLoader`) with 900-char chunks and 120-char overlap. | Successfully ingests multi-page PDFs and Word documents into chunks with metadata. |
| **WS-2** | Enterprise Hybrid RAG Engine | Pinecone dense vector index + BM25 sparse index fused with Reciprocal Rank Fusion ($k=60$). | Exact error codes (`0x80040115`, `ERR-403-VPN`) retrieve relevant policy at Rank 1. |
| **WS-3** | Presidio PII Shield | Analyzer & Anonymizer with custom recognizers for `EMPLOYEE_ID`, `INTERNAL_API_KEY`, and `CREDENTIAL`. | Redacts 100% of detected PII before queries are sent to external LLMs or search APIs. |
| **WS-4** | NeMo Safety Rails | Deterministic and semantic guardrails blocking prompt injection, DAN jailbreaks, and system override attempts. | 100% of tested jailbreak prompts blocked with formal security violation trace. |
| **WS-5** | Keycloak RBAC Enforcement | FastAPI dependency layer validating JWT tokens and enforcing role hierarchy. | Non-admin users receive HTTP 403 Forbidden on document upload; IT support access restricted. |
| **WS-6** | SOC 2 Compliance Audit Ledger | SQLite database logging timestamp, user ID, roles, masked query, latency, and full LangGraph trace. | Audit log entries can be inspected via `/api/audit` by authorized personnel. |
| **WS-7** | Production Cloud Packaging | Hardened Dockerfile with non-root user, curl healthcheck probe, and Uvicorn multi-worker server. | Container starts and responds to healthcheck on port 8080 within 15 seconds. |

---

## 4. Non-Functional Requirements (NFRs) & SLAs

| Requirement | Metric Target | Verification Method |
|---|---|---|
| **Response Latency (p95)** | $\le 2.5 \text{ seconds}$ (Private KB); $\le 4.0 \text{ seconds}$ (Web Fallback) | SQLite audit ledger `latency_ms` tracking |
| **System Availability** | $99.9\% \text{ Uptime}$ | Cloud container healthcheck probe polling `/api/health` |
| **Data Privacy (Zero Leakage)** | $0 \text{ plain-text PII tokens transmitted to cloud LLM}$ | Presidio pre-execution assertion in LangGraph workflow |
| **Security Adherence** | Non-root container execution (UID 10001); No privileged escalation | CIS Docker Benchmark automated scan |
| **Token Authentication** | RS256 Signature verification against Keycloak JWKS | PyJWT cryptographic verification layer |

---

## 5. RACI Governance Matrix

* **R = Responsible**: The role that completes the work.
* **A = Accountable**: The role with final approval authority.
* **C = Consulted**: The role providing input and review.
* **I = Informed**: The role notified of milestone completion.

| Deliverable Milestone | NovaRetail CIO | NovaRetail CISO | IT Service Lead | Lead FDE Architect | DevOps Lead |
|---|:---:|:---:|:---:|:---:|:---:|
| **Discovery & Scope Sign-off** | **A** | **C** | **C** | **R** | **I** |
| **Data Classification & PII Rules** | **I** | **A** | **C** | **R** | **I** |
| **Hybrid RAG & LangGraph Workflow** | **I** | **I** | **C** | **R** | **R** |
| **Keycloak OIDC & RBAC Setup** | **I** | **C** | **A** | **R** | **C** |
| **UAT Execution & Defect Resolution** | **I** | **C** | **A** | **R** | **C** |
| **Production Cloud Cutover & Sign-off** | **A** | **A** | **C** | **R** | **R** |

---

## 6. Project Sign-off & Execution Approvals

By signing below, the parties agree to the scope, deliverables, and acceptance criteria outlined in this Statement of Work.

**For NovaRetail Inc.:**

Signature: _____________________________________  
Name: Marcus Vance  
Title: Chief Information Officer (CIO)  
Date: October 30, 2026  

Signature: _____________________________________  
Name: Elena Rostova  
Title: Chief Information Security Officer (CISO)  
Date: October 30, 2026  

**For AI Solutions Engineering Practice:**

Signature: _____________________________________  
Name: Lead Forward Deployed Engineer  
Title: Principal AI Solutions Architect  
Date: October 30, 2026  

