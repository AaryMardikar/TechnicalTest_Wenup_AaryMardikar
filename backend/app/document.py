import re
from app.models import PersonalWishesState

RELATIONSHIP_WORDS = ["wife", "husband", "spouse", "brother", "sister", "friend", "son", "daughter", "mother", "father", "cousin", "lawyer"]

def generate_draft_document(state: PersonalWishesState) -> str:
    """
    Renders a draft Personal Wishes Document deterministically from validated state.
    Labels the draft explicitly as fictional and not legal advice.
    """
    def format_val(val, default="[Pending Information]"):
        if val is None or val == "":
            return default
        if isinstance(val, bool):
            return "Yes" if val else "No"
        return str(val)

    rel_pattern = r"(?i)^(?:my\s+)?(" + "|".join(RELATIONSHIP_WORDS) + r")[.!]?$"

    # Format children
    if state.has_children is True:
        valid_children = [
            c for c in (state.children_names or [])
            if c and not re.match(r"(?i)^(yes|\d+|two|three|four|\s*)+$", c.strip())
        ]
        if valid_children:
            children_str = ", ".join(valid_children)
        else:
            children_str = "Yes (Names [Pending Information])"
    elif state.has_children is False:
        children_str = "None"
    else:
        children_str = "[Pending Information]"

    # Format executor
    if state.executor and state.executor.name:
        rel = f" ({state.executor.relationship})" if state.executor.relationship else ""
        executor_str = f"{state.executor.name}{rel}"
    else:
        executor_str = "[Pending Information]"

    # Format specific gifts (reject post-mortem and relationship words)
    valid_gifts = [
        g for g in (state.specific_gifts or [])
        if g and g.strip().lower() not in ["none", "none specified", "no", "n/a", "no gifts"]
        and not re.match(rel_pattern, g.strip())
        and not any(k in g.lower() for k in ["funeral", "death", "dj", "burial", "cremat"])
    ]
    if valid_gifts:
        gifts_str = "\n".join([f"  - {gift}" for gift in valid_gifts])
    else:
        gifts_str = "  - None specified"

    # Format personal / funeral wishes (reject orphan relationship words)
    valid_wishes = [
        w for w in (state.additional_wishes or [])
        if w and w.strip().lower() not in ["none", "none specified", "no", "n/a", "no wishes"]
        and not re.match(rel_pattern, w.strip())
    ]
    if valid_wishes:
        wishes_str = "\n".join([f"  - {wish}" for wish in valid_wishes])
    else:
        wishes_str = "  - None specified"

    return f"""======================================================================
*** DRAFT PERSONAL WISHES DOCUMENT ***
IMPORTANT NOTICE: THIS IS A FICTIONAL DOCUMENT GENERATED FOR INTAKE 
DEMONSTRATION PURPOSES ONLY. IT DOES NOT CONSTITUTE LEGAL ADVICE.
======================================================================

1. DECLARANT INFORMATION
   Full Name:    {format_val(state.full_name)}
   Home Address: {format_val(state.home_address)}

2. JURISDICTION & ASSET COVERAGE
   Worldwide Assets Covered: {format_val(state.covers_worldwide_assets)}

3. FAMILY & DEPENDENTS
   Children: {children_str}

4. APPOINTMENT OF EXECUTOR
   Primary Executor: {executor_str}

5. SPECIFIC BEQUESTS & GIFTS
{gifts_str}

6. SPECIAL & FUNERAL WISHES
{wishes_str}

======================================================================
Draft generated automatically from confirmed intake responses.
======================================================================"""