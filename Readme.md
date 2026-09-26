

# README.md

```markdown
# Personal Wishes Document Studio

An intelligent legal intake application that converts conversational inputs into a structured, verified **Personal Wishes Document** in real time. Powered by Groq's high-speed LLaMA 3.1 8B inference, FastAPI, and a self-healing state machine.

## Key Features

* **Conversational Legal Intake:** Replaces multi-step web forms with an interactive interview that collects declarant identity, worldwide asset coverage, dependants, executors, bequests, and funeral wishes.
* **Dual-Panel Live Synchronization:** A split workspace showing the interview on the left and real-time updates of the legal draft document and JSON state on the right.
* **Zero Cross-Contamination Guard:** Heuristic state checks and intent guards prevent post-mortem/funeral instructions from being misclassified as gifts or bequests.
* **Resilient Dual-Layer Persistence:** Sessions are automatically saved to `backend/data/sessions/` on disk and cached in browser `localStorage`, ensuring progress is never lost across server restarts or page refreshes.
* **Direct Draft Export:** Single-click export of the drafted document to a clean `.txt` file, formatted and named based on the declarant's identity and creation date.
* **Graceful Fallbacks:** Seamlessly falls back to an internal deterministic state machine if Groq API rate limits or network connection drops occur.

---

## System Architecture

```text
Wenup/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py         # FastAPI routes, static mount & app initialization
│   │   ├── models.py       # Pydantic state schemas & request models
│   │   ├── llm.py          # Groq LLM integration, system prompts & heuristic engine
│   │   ├── service.py      # Session management, disk persistence & state healing
│   │   └── document.py     # Deterministic legal draft rendering engine
│   ├── data/
│   │   └── sessions/       # Persisted session storage (auto-created JSON files)
│   └── tests/
│       └── test_flow.py    # Automated test suite
├── frontend/
│   ├── index.html          # High-conversion landing page with floating About drawer
│   ├── app.html            # Main intake studio workspace (Chat + Live Draft)
│   └── app.js              # State reconciliation, live rendering & download engine
├── .env                    # Environment credentials & model configuration
└── requirements.txt        # Backend dependencies
```

## Getting Started

### 1. Prerequisites
* **Python 3.10+** (Python 3.11 or 3.12 recommended)
* A free **Groq Cloud API Key** (obtainable from [console.groq.com/keys](https://console.groq.com/keys))
* Add your Api key in .env file
---

### 2. Installation & Environment Setup

1. **Clone the repository and enter the directory:**

Create and activate a Python virtual environment:

PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1

Install dependencies:

PowerShell
pip install -r requirements.txt

. Running the Application
Start the FastAPI backend with auto-reload:
PowerShell
uvicorn app.main:app --reload --app-dir backend --port 8000

Access the application:
Landing Page: Open http://localhost:8000/
Intake Studio: Click "Create Document" or navigate directly to http://localhost:8000/app.html
API Docs (Swagger): Open http://localhost:8000/docs

### Production Improvement

1. Data Layer & Scalable PersistenceReplace Flat-File Storage with Managed DB: Migrate data/sessions/*.json to PostgreSQL (using SQLAlchemy or SQLModel) for transactional consistency, with Redis handling active session caching and TTL eviction.Encryption at Rest & in Transit: Encrypt declarant data, dependent names, and executor details at the column level (AES-256 / pgcrypto) to meet data privacy standards (GDPR, CCPA) for sensitive estate-planning information.
  
2. Authentication, Security & GuardrailsUser Authentication & Authorization: Implement OAuth2 / JWT authentication (or providers like Clerk/Auth0) to replace client-generated random session IDs, ensuring users only access their own drafts.LLM Security & Prompt Injection Defense: Add input sanitization and an adversarial guardrail layer (such as NeMo Guardrails or Llama Guard) to prevent prompt injections designed to manipulate state extraction or bypass document boundaries.Rate Limiting & Abuse Prevention: Add IP- and token-based rate limiting via Redis (slowapi for FastAPI) to prevent Groq API quota exhaustion.

3. LLM Reliability & ResiliencyMulti-Provider Failover: Configure automatic fallback routing (e.g., Groq $\rightarrow$ OpenAI $\rightarrow$ Anthropic) in case of rate limits, network timeouts, or provider downtime.Structured Tool Calling: Migrate from raw JSON-mode string extraction to native function/tool calling (e.g., Pydantic schema passed directly to the model API) for more deterministic parameter binding.Observability & Evaluation Tracing: Integrate OpenTelemetry, LangSmith, or Arize Phoenix to track latency, token consumption, extraction failure rates, and regression benchmarks across model updates.
