import json
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from openai import OpenAI
from app.models import PersonalWishesState, Executor

SYSTEM_PROMPT = """You are an intelligent intake assistant helping a user draft a Personal Wishes Document.
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

OUTPUT SCHEMA:
{
  "extracted_updates": {
    "full_name": string or null,
    "home_address": string or null,
    "covers_worldwide_assets": boolean or null,
    "has_children": boolean or null,
    "children_names": list of strings or null,
    "executor": {
      "name": string or null,
      "relationship": string or null
    } or null,
    "specific_gifts": list of strings or null,
    "additional_wishes": list of strings or null
  },
  "assistant_reply": "Your next conversational question or confirmation.",
  "is_complete": boolean
}
"""

RELATIONSHIP_WORDS = ["wife", "husband", "spouse", "brother", "sister", "friend", "son", "daughter", "mother", "father", "cousin", "lawyer"]
FUNERAL_KEYWORDS = ["funeral", "death", "die", "died", "dj", "cremat", "burial", "ashes", "music", "grave", "ceremony", "songs"]

def sanitize_name(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"(?i)^(?:my\s+name\s+is|i\s+am|this\s+is)\s+", "", s)
    s = re.sub(r"(?i)\s+(?:and|&|,)?\s*(?:i\s+live.*|living.*|at.*)?$", "", s)
    s = re.sub(r"(?i)\s+(?:and|&)\s*$", "", s)
    return s.strip().title()

def sanitize_address(raw: str) -> str:
    s = raw.strip()
    s = re.sub(r"(?i)^.*?(?:live\s+in|living\s+at|residing\s+at|address\s+is|at)\s+", "", s)
    return s.strip()

def clean_executor_name(raw: str) -> str:
    s = raw.strip()
    patterns = [
        r"(?i)^(?:i\s+(?:want|would\s+like)\s+to\s+)?(?:please\s+)?(?:appoint|rename|change|make|set)?\s*(?:my\s+)?(?:appointment\s+of\s+)?(?:primary\s+)?executor\s*(?:as|to|is)?\s*(?:a\s+)?(?:name\s+)?(?:is\s+)?\s*",
        r"(?i)^(?:my\s+)?(?:executor\s+is|executor\s+to)\s*",
        r"(?i)^(?:actually\s+)?(?:make\s+it|change\s+to)\s*",
        r"(?i)^name\s+(?:is\s+)?",
    ]
    for pat in patterns:
        s = re.sub(pat, "", s).strip()
    return s

def clean_children_names(raw: str) -> List[str]:
    s = raw.strip()
    s = re.sub(r"(?i)\s+not\s+(?:the\s+)?(?:appointment\s+of\s+)?executor.*$", "", s)
    s = re.sub(r"(?i)^(?:the\s+)?(?:names?\s+of\s+)?(?:my\s+)?(?:children\s+(?:are|is)|kids\s+(?:are|is))\s*", "", s).strip()
    tokens = re.split(r",|\band\b|&", s)
    names = []
    for token in tokens:
        clean = token.strip()
        clean = re.sub(r"^\d+[\.\)\s]+", "", clean).strip()
        if clean and not re.match(r"(?i)^(i\s+have|\d+|two|three|four|yes|no|children|kids)$", clean):
            names.append(clean.title())
    return names

def extract_heuristically(current_state: PersonalWishesState, history: List[Dict[str, str]], message: str) -> Dict[str, Any]:
    msg = message.strip()
    msg_lower = msg.lower()
    updates: Dict[str, Any] = {}

    last_assistant_msg = ""
    for turn in reversed(history):
        if turn.get("role") == "assistant":
            last_assistant_msg = turn.get("content", "").lower()
            break

    is_prompting_funeral = "personal or funeral" in last_assistant_msg or "funeral wishes" in last_assistant_msg
    is_prompting_gifts = ("specific gifts" in last_assistant_msg or "bequests" in last_assistant_msg) and not is_prompting_funeral

    # 1. FUNERAL / DEATH WISHES
    if any(k in msg_lower for k in FUNERAL_KEYWORDS) or is_prompting_funeral:
        if any(neg in msg_lower for neg in ["no", "none", "nothing", "skip", "n/a", "no wishes", "done"]):
            updates["additional_wishes"] = ["None specified"]
            reply = "All details have been recorded! Please review your completed draft on the right. You can make adjustments at any time."
        else:
            updates["additional_wishes"] = [msg]
            reply = f"I have recorded that in your personal and funeral wishes. Your draft document on the right is now complete! Let me know if you would like to make any adjustments."
        return {"extracted_updates": updates, "assistant_reply": reply, "is_complete": True}

    # 2. NEGATION / SKIP ("none", "no", "skip")
    if re.match(r"^(?:no|none|nothing|skip|n/?a|no\s+gifts?)[.!]?$", msg_lower):
        if is_prompting_gifts or not current_state.specific_gifts:
            updates["specific_gifts"] = ["None specified"]
            reply = "Noted, no specific gifts. Do you have any personal or funeral wishes you would like to include?"
            return {"extracted_updates": updates, "assistant_reply": reply, "is_complete": False}

    # 3. EXPLICIT CORRECTIONS
    name_corr = re.search(r"(?i)(?:i\s+want\s+to\s+)?(?:rename|change|update|correct|set)\s+(?:my\s+)?(?:full\s+)?name\s*(?:to|is|as)?\s*(.+)$", msg)
    if name_corr:
        new_name = name_corr.group(1).strip().title()
        new_name = re.sub(r"[.\",']", "", new_name)
        updates["full_name"] = new_name
        return {"extracted_updates": updates, "assistant_reply": f"I have updated your legal name to {new_name}.", "is_complete": False}

    addr_corr = re.search(r"(?i)(?:i\s+want\s+to\s+)?(?:change|update|correct|set|move)\s+(?:my\s+)?(?:home\s+)?address\s*(?:to|is|as)?\s*(.+)$", msg)
    if addr_corr:
        new_addr = addr_corr.group(1).strip()
        updates["home_address"] = new_addr
        return {"extracted_updates": updates, "assistant_reply": f"I have updated your address to {new_addr}.", "is_complete": False}

    # 4. SPECIFIC GIFTS
    if is_prompting_gifts:
        updates["specific_gifts"] = [msg]
        reply = f"Recorded gift: \"{msg}\". Do you have any personal or funeral wishes you would like to include?"
        return {"extracted_updates": updates, "assistant_reply": reply, "is_complete": False}

    # 5. EXECUTOR APPOINTMENT
    prompted_for_executor = "primary executor" in last_assistant_msg or "what is their full legal name" in last_assistant_msg

    if "executor" in msg_lower or "appoint" in msg_lower or prompted_for_executor:
        rel_pattern = r"\b(" + "|".join(RELATIONSHIP_WORDS) + r")\b"
        rel_match = re.search(rel_pattern, msg_lower)

        pure_rel = re.match(r"^(?:my\s+)?(" + "|".join(RELATIONSHIP_WORDS) + r")[.!]?$", msg_lower)
        if pure_rel:
            rel = pure_rel.group(1).lower()
            current_name = current_state.executor.name if current_state.executor else None
            updates["executor"] = {"name": current_name, "relationship": rel}
            return {
                "extracted_updates": updates,
                "assistant_reply": f"Understood, your {rel}. What is their full legal name?",
                "is_complete": False
            }

        existing_rel = current_state.executor.relationship if current_state.executor else "appointed executor"
        relationship = rel_match.group(1).lower() if rel_match else existing_rel

        name_clean = clean_executor_name(msg)
        name_clean = re.sub(rel_pattern, "", name_clean, flags=re.IGNORECASE)
        name_clean = re.sub(r"(?i)\b(my|the|a|name|is|as)\b", "", name_clean)
        name_clean = re.sub(r"[()\[\]]", "", name_clean).strip().title()

        if name_clean and len(name_clean) > 1 and name_clean.lower() not in ["none", "no", "skip"]:
            updates["executor"] = {"name": name_clean, "relationship": relationship}
            reply = f"I have appointed {name_clean} ({relationship}) as your executor. Do you have any specific gifts or bequests to include? (Say 'none' to skip)"
            return {"extracted_updates": updates, "assistant_reply": reply, "is_complete": False}
        elif prompted_for_executor and not pure_rel and msg_lower not in ["none", "no"]:
            name_direct = msg.strip().title()
            updates["executor"] = {"name": name_direct, "relationship": existing_rel}
            reply = f"I have appointed {name_direct} ({existing_rel}) as your executor. Do you have any specific gifts or bequests to include? (Say 'none' to skip)"
            return {"extracted_updates": updates, "assistant_reply": reply, "is_complete": False}

    # 6. DECLARANT INFORMATION (Name & Address Gatekeeper)
    if not current_state.full_name or not current_state.home_address:
        if current_state.full_name and not current_state.home_address:
            addr = sanitize_address(msg)
            updates["home_address"] = addr or msg
            reply = f"Thank you, {current_state.full_name}. Does this document cover worldwide assets or local assets only?"
            return {"extracted_updates": updates, "assistant_reply": reply, "is_complete": False}

        if any(w in msg_lower for w in ["live in", "living at", "address is", "apartment", "nagar", "road", "street"]):
            addr_match = re.search(r"(?:live in|address is|living at|at)\s+(.+)$", msg, re.IGNORECASE)
            updates["home_address"] = addr_match.group(1).strip() if addr_match else msg
            name_candidate = sanitize_name(msg.split(",")[0])
            if name_candidate and not any(w in name_candidate.lower() for w in ["live", "apartment", "nagar", "road"]):
                updates["full_name"] = name_candidate
        else:
            updates["full_name"] = sanitize_name(msg)

        has_name = bool(updates.get("full_name") or current_state.full_name)
        has_addr = bool(updates.get("home_address") or current_state.home_address)

        if has_name and not has_addr:
            fn = updates.get("full_name") or current_state.full_name
            reply = f"Thank you, {fn}. What is your current residential or home address?"
            return {"extracted_updates": updates, "assistant_reply": reply, "is_complete": False}
        else:
            fn = updates.get("full_name") or current_state.full_name
            reply = f"Thank you, {fn}. Does this document cover worldwide assets or local assets only?"
            return {"extracted_updates": updates, "assistant_reply": reply, "is_complete": False}

    # 7. WORLDWIDE ASSETS
    if current_state.covers_worldwide_assets is None or "worldwide assets" in last_assistant_msg:
        if any(w in msg_lower for w in ["worldwide", "global", "local", "india only", "yes", "no"]):
            is_worldwide = any(w in msg_lower for w in ["worldwide", "global", "yes"])
            updates["covers_worldwide_assets"] = is_worldwide
            return {"extracted_updates": updates, "assistant_reply": "Noted. Do you have any children?", "is_complete": False}

    # 8. CHILDREN
    if current_state.has_children is None or "do you have any children" in last_assistant_msg or "names of your children" in last_assistant_msg:
        if any(neg in msg_lower for neg in ["no", "none", "don't", "dont", "zero", "n/a"]):
            updates["has_children"] = False
            updates["children_names"] = []
            reply = "Understood. Who would you like to appoint as your primary executor (e.g., spouse, family member, or friend)?"
            return {"extracted_updates": updates, "assistant_reply": reply, "is_complete": False}

        updates["has_children"] = True
        names = clean_children_names(msg)
        if names:
            updates["children_names"] = names
            reply = f"Recorded children: {', '.join(names)}. Who would you like to appoint as your primary executor (e.g., spouse, family member, or friend)?"
        else:
            reply = "Got it! Could you please share the names of your children?"
        return {"extracted_updates": updates, "assistant_reply": reply, "is_complete": False}

    # 9. FALLBACK
    if msg_lower in RELATIONSHIP_WORDS or re.match(r"^(?:my\s+)?(" + "|".join(RELATIONSHIP_WORDS) + r")$", msg_lower):
        rel = msg_lower.replace("my ", "").strip()
        updates["executor"] = {"name": (current_state.executor.name if current_state.executor else None), "relationship": rel}
        return {"extracted_updates": updates, "assistant_reply": f"Understood, your {rel}. What is their full legal name?", "is_complete": False}

    updates["additional_wishes"] = [msg]
    return {
        "extracted_updates": updates,
        "assistant_reply": "I have added that to your personal wishes. Let me know if you would like to make any other adjustments.",
        "is_complete": True
    }

class BaseLLMClient(ABC):
    @abstractmethod
    def process_turn(
        self,
        current_state: PersonalWishesState,
        history: List[Dict[str, str]],
        user_message: str
    ) -> Dict[str, Any]:
        pass

class OpenAILikeClient(BaseLLMClient):
    def __init__(self, base_url: str, api_key: str, model: str):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def process_turn(
        self,
        current_state: PersonalWishesState,
        history: List[Dict[str, str]],
        user_message: str
    ) -> Dict[str, Any]:
        state_context = f"CURRENT STATE:\n{current_state.model_dump_json(indent=2)}"
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": state_context}
        ]
        for turn in history[-6:]:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            raw = response.choices[0].message.content.strip()
            match = re.search(r"\{[\s\S]*\}", raw)
            data = json.loads(match.group(0)) if match else json.loads(raw)

            extracted = data.get("extracted_updates", {})
            if isinstance(extracted, dict):
                # Ensure post-mortem wishes never remain misclassified as gifts
                gifts = extracted.get("specific_gifts")
                if isinstance(gifts, list):
                    for g in list(gifts):
                        if any(k in str(g).lower() for k in FUNERAL_KEYWORDS):
                            gifts.remove(g)
                            if not extracted.get("additional_wishes"):
                                extracted["additional_wishes"] = []
                            extracted["additional_wishes"].append(g)

            return data
        except Exception:
            return extract_heuristically(current_state, history, user_message)

class MockLLMClient(BaseLLMClient):
    def process_turn(
        self,
        current_state: PersonalWishesState,
        history: List[Dict[str, str]],
        user_message: str
    ) -> Dict[str, Any]:
        msg_l = user_message.lower()
        if "jane smith" in msg_l and "123 high st" in msg_l:
            return {
                "extracted_updates": {
                    "full_name": "Jane Smith",
                    "home_address": "123 High St, London",
                    "has_children": False
                },
                "assistant_reply": "Thank you, Jane. Does this document cover worldwide assets or UK-only?",
                "is_complete": False
            }
        if "brother james" in msg_l:
            return {
                "extracted_updates": {
                    "executor": {"name": "James Smith", "relationship": "brother"}
                },
                "assistant_reply": "Got it. I have noted James Smith (brother) as executor. Do you have any specific gifts to allocate?",
                "is_complete": False
            }
        if "sister sarah instead" in msg_l or "change executor to sarah" in msg_l:
            return {
                "extracted_updates": {
                    "executor": {"name": "Sarah Smith", "relationship": "sister"}
                },
                "assistant_reply": "I've updated your executor to your sister, Sarah Smith. Any other changes?",
                "is_complete": False
            }
        if "malformed" in msg_l:
            return {
                "extracted_updates": "INVALID_TYPE",
                "assistant_reply": "Broken response test",
                "is_complete": False
            }

        return extract_heuristically(current_state, history, user_message)