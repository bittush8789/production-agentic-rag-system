# Enterprise IT Support Agentic RAG Copilot (Enterprise Edition)

A production-grade **Enterprise AI Integration System** engineered for corporate environments. Built with **LangGraph, FastAPI, Pinecone, BM25 Hybrid Retrieval, Microsoft Presidio, NVIDIA NeMo Guardrails, Keycloak OIDC/RBAC, and Docker**.

---

## 📚 Complete Documentation Navigation

All architectural, deployment, and Forward Deployed Engineer (FDE) consulting lifecycle documents are located in the [`docs/`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/) directory:

| Documentation Topic | File Link | Target Audience | Description |
|---|---|---|---|
| **Master Documentation Index** | [`docs/README.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/README.md) | All Teams | Centralized index of all technical and consulting documentation. |
| **Standalone Single EC2 Deployment** | [`docs/EC2_STANDALONE_DEPLOYMENT.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/EC2_STANDALONE_DEPLOYMENT.md) | Developers & DevOps | **Step-by-step single EC2 deployment guide** (Docker & Systemd, without ALB/ASG). |
| **AWS EC2 ALB & Auto Scaling** | [`docs/AWS_EC2_ALB_AUTOSCALING_DEPLOYMENT.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/AWS_EC2_ALB_AUTOSCALING_DEPLOYMENT.md) | Cloud Engineers | Production deployment with Application Load Balancer & Auto Scaling using Windows PowerShell and AWS CLI. |
| **FDE Consulting Lifecycle** | [`docs/FDE_CONSULTING_LIFECYCLE.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/FDE_CONSULTING_LIFECYCLE.md) | Leadership & Engineers | High-level summary of the 5-phase FDE consulting methodology. |
| **FDE Playbook & Architecture** | [`docs/FDE_PLAYBOOK_AND_ARCHITECTURE.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/FDE_PLAYBOOK_AND_ARCHITECTURE.md) | Architects & DevOps | 8-week engagement roadmap, detailed sequence diagrams, and multi-cloud runbooks. |
| **Architecture Statement of Work (SOW)** | [`docs/FDE_ARCHITECTURE_SOW.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/FDE_ARCHITECTURE_SOW.md) | CIO, CISO, Legal | Formal contract deliverables, SLAs, Non-Functional Requirements, and RACI governance matrix. |
| **Enterprise Business Case & ROI** | [`docs/FDE_BUSINESS_CASE_ROI.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/FDE_BUSINESS_CASE_ROI.md) | CFO, CIO, Finance | Financial modeling: 65% ticket deflection, $1.22M net savings, 2,234% ROI, 16-day payback. |
| **UAT Runbook & Test Execution** | [`docs/FDE_UAT_RUNBOOK.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/FDE_UAT_RUNBOOK.md) | QA, InfoSec, IT Ops | 10 verified test scenarios with exact test inputs, curl commands, and acceptance outcomes. |

---

## 🚀 Key Enterprise Capabilities

### 1. Enterprise Hybrid RAG Retrieval (Dense + Sparse BM25 Fusion)
**The application features true Enterprise Hybrid RAG.**
- **Problem in Traditional RAG**: Standard systems rely purely on Dense Vector Search via embeddings. In real-world enterprise environments, pure semantic search frequently fails to locate exact technical error codes (e.g., `0x80040115`, `ERR_VPN_TIMEOUT`), command lines (`gpupdate /force`), or corporate policy identifiers (`SEC-POL-04`).
- **Hybrid RAG Solution with Reciprocal Rank Fusion (RRF)**:
  - **Dense Vector Search**: Captures conceptual semantics, synonyms, and natural language intent.
  - **Sparse Keyword Search (BM25)**: Matches exact keywords, acronyms, and technical error strings.
  - **Reciprocal Rank Fusion (RRF)**: Merges the ranked outputs dynamically using:
    $$RRF\_Score(d) = \frac{w_{dense}}{60 + Rank_{dense}(d)} + \frac{w_{bm25}}{60 + Rank_{bm25}(d)}$$
  - Returns deduplicated, grounded evidence chunks with source attribution and citation traceability.

---

### 2. Enterprise Security & Guardrails Architecture

```text
                  [ Employee / Client Request ]
                               │
                               ▼
        ┌──────────────────────────────────────────────┐
        │       Keycloak OIDC & RBAC Enforcement       │
        │   - JWT Bearer Token Validation (RS256 JWKS) │
        │   - Roles: Employee | IT Support | Admin     │
        └──────────────────────┬───────────────────────┘
                               │
                               ▼
        ┌──────────────────────────────────────────────┐
        │      Microsoft Presidio PII Guardrail        │
        │   - Detects: Emails, Phones, SSNs, API Keys  │
        │   - Redacts PII before LLM / Search / Cloud  │
        └──────────────────────┬───────────────────────┘
                               │
                               ▼
        ┌──────────────────────────────────────────────┐
        │            NVIDIA NeMo Guardrails            │
        │   - Input Rails: Jailbreak / Prompt Injection│
        │   - Scope Rails: Off-Topic / Malware Filter  │
        └──────────────┬───────────────────────────────┘
                       │
           ┌───────────┴───────────┐
           │ ALLOWED               │ BLOCKED
           ▼                       ▼
    [ LangGraph Workflow ]   [ Immediate Security Alert ]
           │                 - Policy: SEC-POL-01
           │                 - Logged to SOC 2 Audit DB
           ▼
    ┌───────────────────────────────────┐
    │     Hybrid RAG Retrieval Engine   │
    │  - Pinecone Dense Vector Search   │
    │  - Sparse BM25 Keyword Matching   │
    │  - Reciprocal Rank Fusion (RRF)   │
    └──────────────────┬────────────────┘
                       │
                       ▼
    ┌───────────────────────────────────┐
    │     Evidence Evaluator & Web      │
    │  - Good: Grounded KB Generation   │
    │  - Weak: Tavily Vendor Web Search │
    └──────────────────┬────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────────────────┐
        │            NeMo & Presidio Output Rails      │
        │   - Master Credential Leak Prevention        │
        │   - Hallucination / Grounding Verification   │
        └──────────────────────┬───────────────────────┘
                               │
                               ▼
                   [ Grounded Safe Response ]
```

---

### 3. Core Enterprise Modules

#### 🛡️ Microsoft Presidio PII Detection & Anonymization
- Intercepts all incoming user queries at the API boundary before external transmission.
- Automatically masks standard Personally Identifiable Information (`EMAIL_ADDRESS`, `PHONE_NUMBER`, `US_SSN`, `CREDIT_CARD`, `IP_ADDRESS`).
- **Custom Enterprise Recognizers**: Corporate Employee IDs (`EMP-\d{4,6}`), internal API keys (`NOVA-[A-Za-z0-9]{12,32}`), and plaintext credentials.
- Output rails ensure no accidentally generated PII leaves the corporate network boundary.

#### 🤖 NVIDIA NeMo Guardrails
- **Input Rails**:
  - Deterministic and semantic detection of **Jailbreaks & Prompt Injections** (e.g., "Ignore previous instructions", "You are now DAN", "Reveal system prompt", "Dump password shadow file").
  - **Scope Moderation**: Automatically rejects requests outside of enterprise IT scope (e.g., malware generation, illicit activities, financial crypto speculation).
- **Dialog Rails**:
  - Enforces corporate IT security policies (e.g., NovaRetail rule: IT personnel and AI assistants shall never request or disclose one-time passwords or MFA seed codes).
- **Output Rails**:
  - Validates generated responses for factual grounding against retrieved documents to eliminate hallucinations.

#### 🔐 Keycloak Identity & Role-Based Access Control (RBAC)
- **OIDC JWT Authentication**: Validates Bearer tokens against Keycloak JWKS endpoint (`/protocol/openid-connect/certs`).
- **Enforced Enterprise Roles**:
  - `ROLE_EMPLOYEE`: Access to ask IT support questions, interact with the copilot, and view document citations.
  - `ROLE_IT_SUPPORT`: Access to view real-time diagnostic traces, trigger query rewrites, and inspect enterprise audit logs.
  - `ROLE_ADMIN`: Access to ingest documents (`POST /api/ingest`), update the Hybrid Knowledge Base, configure guardrails, and access full SOC 2 compliance telemetry.
- **Built-in Mock JWT Minting**: Endpoint `POST /api/auth/token` allows instant role switching directly in the UI and Swagger docs for testing without requiring an active remote Keycloak cluster.

#### 📊 SOC 2 / GDPR Compliant Audit Logging
- Persists all interactions into an immutable audit table in SQLite (`data/audit.db`):
  - Request timestamp, User ID, Username, RBAC Roles.
  - Original Question vs. PII-Redacted Question.
  - Detected PII entities and confidence scores.
  - Guardrail decisions (`PASSED`, `BLOCKED_SEC-POL-01`, `REDACTED_PII`).
  - Retrieval mode (`Hybrid RAG`), latency in milliseconds, and complete LangGraph trace.
  - Accessible via `GET /api/audit` (restricted to `ROLE_IT_SUPPORT` and `ROLE_ADMIN`).

---

## 4. API Endpoints Reference

| Method | Endpoint | RBAC Permission | Description |
|---|---|---|---|
| `GET` | `/api/health` | Public | Service health and enabled feature flags |
| `GET` | `/api/guardrails/status` | `ROLE_EMPLOYEE`+ | Live operational status of Presidio, NeMo, Keycloak, and Hybrid RAG |
| `POST` | `/api/auth/token` | Public (Dev) | Mint signed JWT tokens for `employee`, `it_support`, or `admin` |
| `GET` | `/api/auth/me` | Authenticated | Decoded token claims, user profile, and verified roles |
| `POST` | `/api/chat` | `ROLE_EMPLOYEE`+ | Main IT Copilot pipeline with Guardrails & Hybrid RAG |
| `POST` | `/api/ingest` | `ROLE_ADMIN` | Upload and index documents into Dense + BM25 stores |
| `GET` | `/api/audit` | `ROLE_IT_SUPPORT`, `ROLE_ADMIN` | Retrieve chronological security and compliance audit logs |

---

## 5. Deployment Options

### Option A: Standalone Single EC2 Instance (Recommended for Quick Setup)
For a straightforward, cost-effective deployment on a single Amazon EC2 instance without Load Balancers or Auto Scaling:
* Follow the dedicated guide: [`docs/EC2_STANDALONE_DEPLOYMENT.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/EC2_STANDALONE_DEPLOYMENT.md)
* Uses Docker or Linux Systemd service on Ubuntu / Amazon Linux (`t3.medium`).

### Option B: High-Availability AWS EC2 + ALB + Auto Scaling (Production)
For enterprise high availability across multiple Availability Zones:
* Follow the complete Windows PowerShell guide: [`docs/AWS_EC2_ALB_AUTOSCALING_DEPLOYMENT.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/AWS_EC2_ALB_AUTOSCALING_DEPLOYMENT.md)
* Includes Amazon ECR container repository, Application Load Balancer (Port 80 to 8080), Target Group (`/api/health` probe), and Auto Scaling Group with Target Tracking (CPU 60%).

### Option C: Containerized Multi-Cloud (ECS, Azure, Cloud Run, Kubernetes)
The application includes a hardened, CIS Docker Benchmark compliant `Dockerfile` (non-root `appuser` UID 10001, healthcheck, and Uvicorn multi-worker):

```bash
# Build the production container
docker build -t enterprise-it-copilot:latest .

# Run container on port 8080
docker run -d \
  -p 8080:8080 \
  -e APP_ENV=production \
  -e ADMIN_API_KEY="your-production-secret-key" \
  --name it-copilot \
  enterprise-it-copilot:latest
```

---

## 6. Local Quickstart (Without Docker)

### Step 1: Install Requirements
```bash
pip install -r requirements.txt
```

### Step 2: Configure Environment (Optional)
Create or edit `.env` in the root folder:
```env
APP_ENV=development
ADMIN_API_KEY=change-me

# LLM Providers (Optional - application includes intelligent local fallback)
OPENAI_API_KEY=your_key_here
PINECONE_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here

# Keycloak Settings (Optional - application includes dev mock tokens)
KEYCLOAK_ENABLED=false
KEYCLOAK_URL=http://localhost:8080
KEYCLOAK_REALM=enterprise
KEYCLOAK_CLIENT_ID=it-support-copilot
```

### Step 3: Run the Application
```bash
python run.py
```

Open:
* Web Application: [http://127.0.0.1:8080](http://127.0.0.1:8080)
* OpenAPI / Swagger Documentation: [http://127.0.0.1:8080/docs](http://127.0.0.1:8080/docs)

---

## 7. Folder Structure Integrity

The original folder structure has been **100% strictly preserved** without adding or modifying any root directories:

```text
Enterprise-IT-Support-Agentic-RAG-Copilot/
├── app/
│   ├── api/
│   │   ├── routes.py          # RBAC-protected chat, auth, ingest, and audit endpoints
│   │   └── __init__.py
│   ├── core/
│   │   ├── config.py          # Centralized settings & guardrail configs
│   │   ├── logging.py         # Structured logging configuration
│   │   ├── security.py        # Keycloak OIDC JWT validation & RBAC dependencies
│   │   └── __init__.py
│   ├── rag/
│   │   ├── state.py           # LangGraph AgentState with telemetry
│   │   ├── vectorstore.py     # Hybrid RAG: Dense Vector + BM25 with RRF
│   │   ├── workflow.py        # LangGraph Workflow with Presidio & NeMo Rails
│   │   └── __init__.py
│   ├── services/
│   │   ├── audit.py           # SQLite SOC 2 / GDPR compliance logging
│   │   ├── guardrails.py      # Microsoft Presidio & NVIDIA NeMo engines
│   │   ├── ingestion.py       # Multi-format document parser & chunker
│   │   └── __init__.py
│   └── main.py                # FastAPI entry with security headers & middleware
├── data/
│   ├── audit.db               # Enterprise query & audit ledger
│   └── sample_kb/             # Baseline company IT policies & runbooks
├── docs/                      # Architectural & FDE documentation suite
├── static/
│   ├── css/style.css          # Enterprise UI styling with security badges
│   └── js/app.js              # Keycloak RBAC client & real-time telemetry
├── templates/
│   └── index.html             # Role switcher, interactive chat, and audit modals
├── uploads/                   # Enterprise uploaded documents
├── Dockerfile                 # Production non-root container configuration
├── requirements.txt           # Enterprise dependencies
├── run.py                     # Entry point
└── README.md                  # Comprehensive documentation
```
