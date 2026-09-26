import pytest
from app.models import PersonalWishesState
from app.llm import MockLLMClient
from app.service import IntakeService
from app.document import generate_draft_document

@pytest.fixture
def intake_service():
    mock_llm = MockLLMClient()
    return IntakeService(llm_client=mock_llm)

def test_multi_field_extraction(intake_service):
    """Handles multiple fields in a single answer."""
    res = intake_service.handle_turn(
        "test-sess-1",
        "I am Jane Smith, living at 123 High St, and I have no children."
    )
    state: PersonalWishesState = res["state"]
    assert state.full_name == "Jane Smith"
    assert state.home_address == "123 High St, London"
    assert state.has_children is False
    assert "Does this document cover worldwide assets" in res["assistant_reply"]

def test_state_correction(intake_service):
    """User updates/corrects an executor previously provided."""
    # First turn sets brother James
    intake_service.handle_turn("test-sess-2", "My brother James will be executor")
    sess = intake_service.get_session("test-sess-2")
    assert sess.state.executor.name == "James Smith"
    assert sess.state.executor.relationship == "brother"

    # Second turn corrects executor to sister Sarah
    res = intake_service.handle_turn("test-sess-2", "Actually, please change executor to Sarah instead")
    assert res["state"].executor.name == "Sarah Smith"
    assert res["state"].executor.relationship == "sister"

def test_malformed_llm_payload_resilience(intake_service):
    """Malformed LLM output is rejected gracefully without corrupting current state."""
    # First turn sets valid state
    intake_service.handle_turn("test-sess-3", "Jane Smith 123 High St")
    
    # Second turn triggers a malformed response from the mock
    res = intake_service.handle_turn("test-sess-3", "send malformed payload")
    
    # State remains intact
    assert res["state"].full_name == "Jane Smith"
    assert res["state"].home_address == "123 High St, London"

def test_document_generation_disclaimer_and_pending_tags():
    """Draft document includes fictional notice and proper placeholders."""
    state = PersonalWishesState(full_name="Jane Smith")
    doc = generate_draft_document(state)
    
    assert "THIS IS A FICTIONAL DOCUMENT" in doc
    assert "DOES NOT CONSTITUTE LEGAL ADVICE" in doc
    assert "Full Name:    Jane Smith" in doc
    assert "Home Address: [Pending Information]" in doc