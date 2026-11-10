from dataclasses import dataclass
from enum import Enum


class ProcessingMode(str, Enum):
    LOCAL_ONLY = "LOCAL_ONLY"
    REDACTED_AI = "REDACTED_AI"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


@dataclass
class PrivacyDecision:
    mode: ProcessingMode
    reason: str
    ai_required: bool
    manual_review_required: bool


def choose_processing_mode(
    local_extraction_reliable: bool,
    sanitized_context_available: bool,
) -> PrivacyDecision:
    if local_extraction_reliable:
        return PrivacyDecision(
            mode=ProcessingMode.LOCAL_ONLY,
            reason="Structured local extraction succeeded.",
            ai_required=False,
            manual_review_required=False,
        )
    if sanitized_context_available:
        return PrivacyDecision(
            mode=ProcessingMode.REDACTED_AI,
            reason="Safe AI interpretation is required.",
            ai_required=True,
            manual_review_required=False,
        )
    return PrivacyDecision(
        mode=ProcessingMode.MANUAL_REVIEW_REQUIRED,
        reason="Safe automated interpretation unavailable.",
        ai_required=False,
        manual_review_required=True,
    )
