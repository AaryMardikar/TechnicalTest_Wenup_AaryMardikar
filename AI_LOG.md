# AI Engineering & Development Log: Personal Wishes Intake Assistant

## 1. Executive Summary & Objective
The primary goal of this system is to replace rigid, high-drop-off legal web forms with a fluid, conversational intake agent capable of gathering information for a **Personal Wishes Document**. The system is built around a hybrid architecture: an LLM-driven conversational front-end running on Groq (`llama-3.1-8b-instant`) backed by a deterministic, self-healing state machine to enforce legal drafting boundaries and eliminate data cross-contamination.

---

## 2. Model Selection, Performance & Constraints

### 2.1 Why Groq + LLaMA 3.1 8B Instant?
* **Sub-Second Latency:** Average time-to-first-token (TTFT) on Groq LPUs ranges between 150ms and 280ms, enabling real-time conversational drafting without noticeable UI lag.
* **Cost & Accessibility:** Groq's free tier provides **14,400 requests/day (RPD)**, **30 requests/minute (RPM)**, and **500,000 tokens/day (TPD)** for `llama-3.1-8b-instant`, which comfortably supports 1,400+ full multi-turn interview sessions daily without API overhead.
* **Deterministic Structured JSON Mode:** Supporting `response_format={"type": "json_object"}` allows the LLM to output valid JSON matching our Pydantic schema, eliminating markdown parsing issues and hallucinated conversational preambles.

---

## 3. System Prompt Engineering Evolution

### 3.1 Initial Architecture & Challenges
Early iterations relied on standard text extraction prompts. When users entered conversational inputs or combined multiple facts into one message, several extraction failures occurred:
1. **Empty Slot Overwrite:** Saying "none" when asked about gifts overwrote previously captured executor details or set the executor's name to `"None"`.
2. **Post-Mortem Cross-Contamination:** Wishes like *"I want full on DJ on my funeral"* or *"buried in native place"* were misclassified as `specific_gifts` because the system saw an empty gifts list before checking wishes.
3. **Conversational Command Bleed:** Revision messages like *"i want to rename my name to Aary Aniruddha Mardikar"* were appended as bullet items under `additional_wishes`.
4. **Premature Step Progression:** Entering only a name prompted the system to ask about worldwide assets, skipping the residential home address entirely.

### 3.2 Final System Prompt Design
The prompt operates under strict role-definition and schema guarantees:

```text
You are an intelligent intake assistant helping a user draft a Personal Wishes Document.
Your job is to conduct a multi-turn conversational interview to gather:
1. Full legal name
2. Home address
3. Whether the document covers worldwide assets (True/False)
4. Whether the user has children (True/False), and their names if applicable
5. Executor's full name and their relationship to the user (e.g. spouse, brother, friend)
6. Any specific gifts or bequests
7. Any additional personal or funeral wishes

CRITICAL INTERVIEW RULES:
- Post-mortem, funeral, death, and ceremony instructions (e.g. DJ, music, burial, cremation, death day) belong EXCLUSIVELY in additional_wishes, NEVER in specific_gifts.
- If the user says "none", "no", or "skip", mark that category as empty. Do NOT assign "none" as an executor or person's name.
- Explicit corrections take priority over general flow.
- Maintain conversation context and output valid JSON ONLY matching the schema below.

4. Key Failure Modes & Defensive Engineering4.1 Address Gatekeeper (Skip Prevention)Problem: Users entering only "Aary Mardikar" saw the assistant respond with "Does this document cover worldwide assets or local assets only?", leaving home_address as [Pending Information].Resolution: Implemented an explicit gatekeeper check in process_turn and extract_heuristically:Pythonnew_name = extracted.get("full_name") or current_state.full_name
new_addr = extracted.get("home_address") or current_state.home_address
if new_name and not new_addr:
    data["assistant_reply"] = f"Thank you, {new_name}. What is your current residential or home address?"
    data["is_complete"] = False

4.2 Executor Two-Step Resolution & Command StrippingProblem: When asked for an executor, typing "friend" caused the assistant to assign "friend" into additional_wishes or specific_gifts. Verbose phrases like "I want to appoint my appointment of executor as a name Rohit Kindarle" were saved as the full raw string.Resolution:Identified relationship tokens (wife, husband, friend, brother, etc.). If a user submits only a relationship token, the system captures relationship = "friend" and prompts: "Understood, your friend. What is their full legal name?"Applied regex filters in clean_executor_name() to strip command patterns (appoint, appointment of executor as, my executor is) before saving the name.4.3 Intent Isolation for Post-Mortem vs. Gift ItemsProblem: When users answered "none" to gifts and followed with "I want full on DJ on my funeral", the prompt context still contained the word "gifts", causing the model to record the DJ wish under specific_gifts.Resolution:Added FUNERAL_KEYWORDS = ["funeral", "death", "die", "died", "dj", "cremat", "burial", "ashes", "music", "grave", "ceremony", "songs"].Any message containing a funeral keyword is routed to additional_wishes.Added a self-healing sanitizer (_heal_state) in service.py that checks specific_gifts on every turn; if any item contains post-mortem language, it automatically transfers it to additional_wishes and resets specific_gifts to ["None specified"].4.4 Circular Import & Windows Terminal EscapingCircular Import Fix: Removed the self-import from app.llm import BaseLLMClient inside backend/app/llm.py, isolating declarations cleanly across models.py, llm.py, and service.py.PowerShell Escape Trap: PowerShell strips single quotes before sending strings to curl.exe, turning {"model": "llama-3.1-8b-instant"} into invalid JSON. Resolved by using PowerShell-native Invoke-RestMethod and relying on the Python SDK inside the backend.5. Dual-Layer Persistence Architecture[Browser Session] 
       │ 
       ├── localStorage (Cached Doc, Cached JSON, Cached History)
       │         ▲ (Instant client-side hydration on F5)
       │         ▼
[FastAPI Backend]
       │
       └── IntakeService (State Machine & Groq Orchestrator)
                 │
                 ▼
       backend/data/sessions/{session_id}.json (Atomic Disk Persistence)
Client-Side Hydration: frontend/app.js pulls from localStorage before network calls finish, eliminating screen flashes or blank input periods upon page refresh.Server-Side Disk Storage: Every state update is committed to backend/data/sessions/{clean_id}.json. If Uvicorn restarts or hot-reloads, the session state is restored without data loss.6. Verification & Automated Test CoverageThe project includes unit and integration tests under tests/test_flow.py covering:Step-by-step state progression (Name $\rightarrow$ Address $\rightarrow$ Assets $\rightarrow$ Children $\rightarrow$ Executor $\rightarrow$ Gifts $\rightarrow$ Wishes).Correct extraction of complex inputs (multi-child lists, corrections to previously entered fields).Strict schema validation via Pydantic v2.Graceful fallback to MockLLMClient and
deterministic state extraction during offline development or test runs.