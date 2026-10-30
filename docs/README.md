# Forward Deployed Engineer (FDE) Documentation Suite

Welcome to the comprehensive **Forward Deployed Engineer (FDE)** documentation repository for the **Enterprise IT Support Agentic RAG Copilot (NovaRetail)**.

This documentation suite covers the complete consulting, engineering, security, and financial lifecycle required to transition an AI initiative from customer problem statement to enterprise production deployment.

---

## 📚 Document Index

| Document Title | File Link | Target Audience | Description |
|---|---|---|---|
| **FDE Consulting Lifecycle** | [`FDE_CONSULTING_LIFECYCLE.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/FDE_CONSULTING_LIFECYCLE.md) | Leadership & Engineers | High-level summary of the 5-phase consulting methodology. |
| **FDE Playbook & Architecture** | [`FDE_PLAYBOOK_AND_ARCHITECTURE.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/FDE_PLAYBOOK_AND_ARCHITECTURE.md) | Architects & DevOps | 8-week engagement roadmap, sequence diagrams, and cloud runbooks. |
| **Architecture Statement of Work (SOW)** | [`FDE_ARCHITECTURE_SOW.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/FDE_ARCHITECTURE_SOW.md) | CIO, CISO, Legal | Formal contract deliverables, SLAs, NFRs, and RACI governance matrix. |
| **Enterprise Business Case & ROI** | [`FDE_BUSINESS_CASE_ROI.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/FDE_BUSINESS_CASE_ROI.md) | CFO, CIO, Finance | Financial modeling: 65% deflection, $1.22M net savings, 2,234% ROI. |
| **UAT Runbook & Sign-off Matrix** | [`FDE_UAT_RUNBOOK.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/FDE_UAT_RUNBOOK.md) | QA, InfoSec, IT Ops | 10 verified test scenarios with exact test inputs and outcomes. |
| **Standalone Single EC2 Deployment** | [`EC2_STANDALONE_DEPLOYMENT.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/EC2_STANDALONE_DEPLOYMENT.md) | Developers & DevOps | **Simple Single EC2 deployment guide** (Docker & Systemd, no ALB/ASG). |
| **AWS EC2 ALB & Auto Scaling Deployment** | [`AWS_EC2_ALB_AUTOSCALING_DEPLOYMENT.md`](file:///d:/Enterprise-IT-Support-Agentic-RAG-Copilot/docs/AWS_EC2_ALB_AUTOSCALING_DEPLOYMENT.md) | DevOps & Cloud Engineers | Complete Windows PowerShell AWS CLI commands for EC2 + ALB + Auto Scaling. |

---

## 🎯 What Makes This an FDE Project?

A Forward Deployed Engineer is responsible for the entire path from customer problem to production value:

```text
Customer Problem
      ↓
Discovery & Requirements   --> docs/FDE_PLAYBOOK_AND_ARCHITECTURE.md
      ↓
Architecture & SOW         --> docs/FDE_ARCHITECTURE_SOW.md
      ↓
Business Case & ROI        --> docs/FDE_BUSINESS_CASE_ROI.md
      ↓
Engineering & Hardening    --> app/ (FastAPI, LangGraph, Presidio, NeMo, Keycloak)
      ↓
UAT Validation             --> docs/FDE_UAT_RUNBOOK.md
      ↓
Cloud Deployment           --> Dockerfile & Cloud Runbooks
```

