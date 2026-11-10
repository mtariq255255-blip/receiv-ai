import json
import re
from dataclasses import dataclass, field
from typing import Any


class PrivacyViolationError(Exception):
    """Raised when an outbound AI request is unsafe."""


@dataclass
class PrivacyContext:
    replacements: dict[str, str] = field(default_factory=dict)
    protected_values: set[str] = field(default_factory=set)


TRN_PATTERN = re.compile(r"(?<!\d)\d{15}(?!\d)")
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
PHONE_PATTERN = re.compile(
    r"(?<!\w)(?:\+971|00971|0)[\s-]?(?:\d[\s-]?){7,10}(?!\w)"
)
LONG_IDENTIFIER_PATTERN = re.compile(r"(?<![A-Za-z0-9])\d{7,}(?![A-Za-z0-9])")
PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\|/)[^\s\"']+")

_SAFE_HEADING_WORDS = {
    "account", "address", "amount", "buyer", "client", "code", "company",
    "currency", "customer", "date", "description", "discount", "due",
    "emirate", "email", "grand", "goods", "gross", "id", "invoice", "item",
    "line", "name", "net", "no", "number", "of", "payable", "payment",
    "per", "place", "price", "product", "qty", "quantity", "rate", "ref",
    "reference", "registration", "seller", "service", "subtotal", "supply",
    "supplier", "tax", "taxable", "total", "trn", "unit", "value", "vat",
    "vendor", "phone", "status", "issued",
}
_HEADING_WORD_PATTERN = re.compile(r"[a-z]+")
_FORBIDDEN_HEADING_TERMS = {
    "ignore", "confidential", "password", "secret", "prompt", "instruction",
    "reveal", "override", "system", "developer", "upload",
}
_FORBIDDEN_KEYS = {
    "filename", "filepath", "file_path", "raw_document", "raw_extraction",
    "document_bytes", "image", "images", "rows", "records", "metadata",
}


def normalize_sensitive_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def protect_value(
    value: Any,
    placeholder: str,
    context: PrivacyContext,
) -> None:
    original = normalize_sensitive_value(value)
    if not original:
        return
    context.replacements[original] = placeholder
    context.protected_values.add(original)


def protect_invoice_fields(invoice: dict, context: PrivacyContext) -> None:
    fields = {
        "supplier_name": "SUPPLIER_1",
        "supplier_trn": "SUPPLIER_TRN_1",
        "supplier_address": "SUPPLIER_ADDRESS_1",
        "customer_name": "BUYER_1",
        "customer_trn": "BUYER_TRN_1",
        "customer_address": "BUYER_ADDRESS_1",
        "customer_email": "BUYER_EMAIL_1",
        "invoice_number": "INVOICE_1",
    }
    for key, placeholder in fields.items():
        protect_value(invoice.get(key), placeholder, context)


def redact_text(text: str, context: PrivacyContext) -> str:
    result = str(text)
    ordered = sorted(
        context.replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for original, placeholder in ordered:
        result = result.replace(original, placeholder)
    result = TRN_PATTERN.sub("TRN_REDACTED", result)
    result = EMAIL_PATTERN.sub("EMAIL_REDACTED", result)
    result = PHONE_PATTERN.sub("PHONE_REDACTED", result)
    return result


def sanitize_column_heading(value: str) -> str | None:
    """Allow only generic invoice vocabulary as an external heading."""
    normalized = re.sub(r"[_-]+", " ", str(value)).strip().lower()
    words = _HEADING_WORD_PATTERN.findall(normalized)
    if not words or any(word in _FORBIDDEN_HEADING_TERMS for word in words):
        return None
    if " ".join(words) != re.sub(r"\s+", " ", normalized):
        return None
    if any(word not in _SAFE_HEADING_WORDS for word in words):
        return None
    return " ".join(words)


def sanitize_column_headings(columns: list[str]) -> dict[str, str]:
    """Return original-heading to safe generic heading for approved labels."""
    sanitized: dict[str, str] = {}
    seen: set[str] = set()
    for column in columns:
        safe = sanitize_column_heading(column)
        if safe is None or safe in seen:
            continue
        sanitized[column] = safe
        seen.add(safe)
    return sanitized


def _validate_payload_values(value: Any, context: PrivacyContext) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).casefold() in _FORBIDDEN_KEYS:
                raise PrivacyViolationError(
                    "Document content or identifying metadata is not allowed in AI requests."
                )
            _validate_payload_values(nested, context)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _validate_payload_values(nested, context)
        return
    if not isinstance(value, str):
        return

    lowered = value.casefold()
    for original in context.protected_values:
        if original and original.casefold() in lowered:
            raise PrivacyViolationError(
                "Protected information detected in AI payload."
            )
    if (
        TRN_PATTERN.search(value)
        or EMAIL_PATTERN.search(value)
        or PHONE_PATTERN.search(value)
        or LONG_IDENTIFIER_PATTERN.search(value)
        or PATH_PATTERN.search(value)
    ):
        raise PrivacyViolationError(
            "A sensitive identifier or file path was detected in AI payload."
        )


def validate_outbound_payload(payload: Any, context: PrivacyContext) -> None:
    try:
        rendered = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as exc:
        raise PrivacyViolationError(
            "AI payload could not be safely serialized."
        ) from exc
    if len(rendered) > 8000:
        raise PrivacyViolationError("AI payload exceeds the privacy input limit.")
    _validate_payload_values(payload, context)


def restore_authorized_placeholders(
    values: dict[str, str],
    context: PrivacyContext,
    allowed_placeholders: set[str],
) -> dict[str, str]:
    """Restore only explicitly approved tokens from structured AI fields."""
    authorized = {
        placeholder: original
        for original, placeholder in context.replacements.items()
        if placeholder in allowed_placeholders
    }
    return {
        key: authorized.get(value, value)
        for key, value in values.items()
    }
