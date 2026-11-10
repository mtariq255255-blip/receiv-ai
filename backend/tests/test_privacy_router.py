from app.services.privacy_router import (
    ProcessingMode,
    choose_processing_mode,
)


def test_reliable_local_extraction_never_uses_ai():
    decision = choose_processing_mode(True, True)
    assert decision.mode is ProcessingMode.LOCAL_ONLY
    assert decision.ai_required is False
    assert decision.manual_review_required is False


def test_ambiguous_extraction_uses_only_available_sanitized_context():
    decision = choose_processing_mode(False, True)
    assert decision.mode is ProcessingMode.REDACTED_AI
    assert decision.ai_required is True


def test_unsafe_extraction_fails_closed_to_manual_review():
    decision = choose_processing_mode(False, False)
    assert decision.mode is ProcessingMode.MANUAL_REVIEW_REQUIRED
    assert decision.ai_required is False
    assert decision.manual_review_required is True
