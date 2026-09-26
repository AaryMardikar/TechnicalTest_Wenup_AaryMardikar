from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class Executor(BaseModel):
    name: Optional[str] = None
    relationship: Optional[str] = None

class PersonalWishesState(BaseModel):
    full_name: Optional[str] = None
    home_address: Optional[str] = None
    covers_worldwide_assets: Optional[bool] = None
    has_children: Optional[bool] = None
    children_names: List[str] = Field(default_factory=list)
    executor: Optional[Executor] = None
    specific_gifts: List[str] = Field(default_factory=list)
    additional_wishes: List[str] = Field(default_factory=list)

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    session_id: str
    assistant_reply: str
    state: PersonalWishesState
    draft_document: str
    is_complete: bool

class SessionStateResponse(BaseModel):
    session_id: str
    state: PersonalWishesState
    draft_document: str
    history: List[Dict[str, str]]