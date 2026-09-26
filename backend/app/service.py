import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.models import PersonalWishesState, Executor
from app.llm import BaseLLMClient, RELATIONSHIP_WORDS, FUNERAL_KEYWORDS
from app.document import generate_draft_document

class SessionData:
    def __init__(self, state: Optional[PersonalWishesState] = None, history: Optional[List[Dict[str, str]]] = None):
        self.state = state or PersonalWishesState()
        self.history = history or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.model_dump(),
            "history": self.history
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionData":
        state = PersonalWishesState(**data.get("state", {}))
        history = data.get("history", [])
        return cls(state=state, history=history)

class IntakeService:
    def __init__(self, llm_client: BaseLLMClient):
        self.llm_client = llm_client
        self.storage_dir = Path(__file__).resolve().parent.parent / "data" / "sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.sessions: Dict[str, SessionData] = {}

    def _get_file_path(self, session_id: str) -> Path:
        clean_id = re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)
        return self.storage_dir / f"{clean_id}.json"

    def _save_to_disk(self, session_id: str):
        if session_id in self.sessions:
            path = self._get_file_path(session_id)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.sessions[session_id].to_dict(), f, indent=2)

    def get_session(self, session_id: str) -> SessionData:
        if session_id not in self.sessions:
            path = self._get_file_path(session_id)
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.sessions[session_id] = SessionData.from_dict(data)
                except Exception:
                    self.sessions[session_id] = SessionData()
            else:
                self.sessions[session_id] = SessionData()
        return self.sessions[session_id]

    def reset_session(self, session_id: str) -> SessionData:
        self.sessions[session_id] = SessionData()
        path = self._get_file_path(session_id)
        if path.exists():
            try:
                path.unlink()
            except Exception:
                pass
        return self.sessions[session_id]

    def handle_turn(self, session_id: str, user_message: str) -> Dict[str, Any]:
        session = self.get_session(session_id)

        raw_output = self.llm_client.process_turn(session.state, session.history, user_message)

        extracted = raw_output.get("extracted_updates", {})
        if isinstance(extracted, dict):
            self._apply_state_delta(session.state, extracted)

        session.history.append({"role": "user", "content": user_message})
        reply = raw_output.get("assistant_reply", "Could you provide more details?")
        session.history.append({"role": "assistant", "content": reply})

        # Self-heal cross-field contaminations
        self._heal_state(session.state)

        self._save_to_disk(session_id)

        draft = generate_draft_document(session.state)
        is_complete = bool(raw_output.get("is_complete", False))

        return {
            "session_id": session_id,
            "assistant_reply": reply,
            "state": session.state,
            "draft_document": draft,
            "is_complete": is_complete
        }

    def _heal_state(self, current: PersonalWishesState):
        """Active state self-healing to eliminate cross-field contamination."""
        rel_pattern = r"(?i)^(?:my\s+)?(" + "|".join(RELATIONSHIP_WORDS) + r")[.!]?$"

        # 1. Purge lone relationship tokens from wishes
        current.additional_wishes = [
            w for w in current.additional_wishes
            if not re.match(rel_pattern, w.strip())
        ]

        # 2. Check if any funeral wish was mistakenly placed in specific_gifts
        misplaced_gifts = [
            g for g in current.specific_gifts
            if any(k in g.lower() for k in FUNERAL_KEYWORDS)
        ]
        if misplaced_gifts:
            for mg in misplaced_gifts:
                current.specific_gifts.remove(mg)
                if mg not in current.additional_wishes:
                    current.additional_wishes.append(mg)

        # 3. Clean defaults
        if not current.specific_gifts:
            current.specific_gifts = ["None specified"]
        if not current.additional_wishes:
            current.additional_wishes = ["None specified"]

    def _apply_state_delta(self, current: PersonalWishesState, updates: Dict[str, Any]):
        rel_pattern = r"(?i)^(?:my\s+)?(" + "|".join(RELATIONSHIP_WORDS) + r")[.!]?$"

        for key, val in updates.items():
            if val is None:
                continue

            if key == "full_name" and val:
                current.full_name = str(val).strip()

            elif key == "home_address" and val:
                current.home_address = str(val).strip()

            elif key == "executor" and isinstance(val, dict):
                current_exec = current.executor or Executor()
                name_val = val.get("name")
                if name_val and str(name_val).strip().lower() not in ["none", "no", "skip", "none specified"]:
                    current_exec.name = str(name_val).strip()
                if "relationship" in val and val["relationship"]:
                    current_exec.relationship = str(val["relationship"]).strip()
                current.executor = current_exec

            elif key == "children_names" and isinstance(val, list):
                cleaned = [
                    str(x).strip() for x in val
                    if str(x).strip() and not re.match(r"(?i)^(yes|\d+|two|three|four|\s*)+$", str(x).strip())
                ]
                if cleaned:
                    current.children_names = list(dict.fromkeys(current.children_names + cleaned))
                if len(current.children_names) > 0:
                    current.has_children = True

            elif key == "specific_gifts" and isinstance(val, list):
                real_gifts = [
                    str(x).strip() for x in val
                    if str(x).strip()
                    and str(x).strip().lower() not in ["none", "none specified", "no", "n/a", "no gifts"]
                    and not re.match(rel_pattern, str(x).strip())
                    and not any(k in str(x).lower() for k in FUNERAL_KEYWORDS)
                ]
                if real_gifts:
                    existing = [g for g in current.specific_gifts if g.lower() not in ["none", "none specified"]]
                    current.specific_gifts = list(dict.fromkeys(existing + real_gifts))
                else:
                    current.specific_gifts = ["None specified"]

            elif key == "additional_wishes" and isinstance(val, list):
                real_wishes = [
                    str(x).strip() for x in val
                    if str(x).strip()
                    and str(x).strip().lower() not in ["none", "none specified", "no", "n/a", "no wishes"]
                    and not re.match(rel_pattern, str(x).strip())
                    and not re.search(r"(?i)\b(rename|change name|update name|correct name|appoint|my name)\b", str(x))
                ]
                if real_wishes:
                    existing = [
                        w for w in current.additional_wishes
                        if w.lower() not in ["none", "none specified"]
                        and not re.match(rel_pattern, w.strip())
                        and not re.search(r"(?i)\b(rename|change name|update name|correct name|appoint|my name)\b", w)
                    ]
                    current.additional_wishes = list(dict.fromkeys(existing + real_wishes))
                else:
                    current.additional_wishes = ["None specified"]

            elif hasattr(current, key):
                setattr(current, key, val)