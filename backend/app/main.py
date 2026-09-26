import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.models import ChatRequest, ChatResponse, SessionStateResponse
from app.llm import OpenAILikeClient, MockLLMClient
from app.service import IntakeService
from app.document import generate_draft_document

load_dotenv()

app = FastAPI(title="Document Intake Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

use_mock = os.getenv("USE_MOCK_LLM", "false").lower() == "true"

if use_mock:
    llm_client = MockLLMClient()
else:
    llm_client = OpenAILikeClient(
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1"),
        api_key=os.getenv("OPENAI_API_KEY", ""),
        model=os.getenv("LLM_MODEL", "llama-3.1-8b-instant")
    )

intake_service = IntakeService(llm_client=llm_client)

@app.post("/api/chat", response_model=ChatResponse)
async def chat_turn(req: ChatRequest):
    try:
        return intake_service.handle_turn(req.session_id, req.message)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/state/{session_id}", response_model=SessionStateResponse)
async def get_state(session_id: str):
    session = intake_service.get_session(session_id)
    return {
        "session_id": session_id,
        "state": session.state,
        "draft_document": generate_draft_document(session.state),
        "history": session.history
    }

@app.post("/api/reset/{session_id}")
async def reset_session(session_id: str):
    intake_service.reset_session(session_id)
    return {"status": "reset", "session_id": session_id}

frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")