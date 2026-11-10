import json
from types import SimpleNamespace

import pytest

from app.agents.document_agent import DocumentIntelligenceAgent
from app.schemas.privacy import AIColumnMapping, AIColumnMappingResult
from app.services.privacy_filter import (
    PrivacyContext,
    PrivacyViolationError,
    validate_outbound_payload,
)
from app.services.private_ai_gateway import map_invoice_columns_with_ai


class FakeResponses:
    def __init__(self, parsed):
        self.parsed = parsed
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.parsed)


class FakeOpenAI:
    instances = []
    result = None

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.responses = FakeResponses(self.result)
        self.instances.append(self)


def test_gateway_sends_only_sanitized_headings(monkeypatch):
    import app.services.private_ai_gateway as gateway

    FakeOpenAI.instances = []
    FakeOpenAI.result = AIColumnMappingResult(mappings=[
        AIColumnMapping(
            column_name="invoice reference",
            field_name="invoice_number",
            confidence=0.99,
        ),
    ])
    monkeypatch.setattr(gateway, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(gateway.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(gateway.settings, "ai_fallback_enabled", True)

    context = PrivacyContext(protected_values={
        "Private Supplier",
        "100123456700003",
        "RAI-PRIVATE-1",
        "buyer@example.test",
        "Confidential consulting work",
        "private-account.pdf",
    })
    mapped = map_invoice_columns_with_ai(
        ["invoice reference", "supplier", "buyer", "service"],
        context,
    )
    assert mapped["mappings"] == {"invoice reference": "invoice_number"}

    client = FakeOpenAI.instances[0]
    request = client.responses.calls[0]
    assert client.init_kwargs["max_retries"] == 0
    assert client.init_kwargs["timeout"] <= 10
    assert "filename" not in request
    assert "metadata" not in request
    assert "Private Supplier" not in str(request)
    assert "100123456700003" not in str(request)
    assert "RAI-PRIVATE-1" not in str(request)
    assert "buyer@example.test" not in str(request)
    assert "Confidential consulting work" not in str(request)
    content = json.loads(request["input"][0]["content"])
    assert content == {
        "task": "map_invoice_columns",
        "columns": ["invoice reference", "supplier", "buyer", "service"],
    }


def test_sensitive_heading_is_blocked_before_sdk_call(monkeypatch):
    import app.services.private_ai_gateway as gateway

    FakeOpenAI.instances = []
    monkeypatch.setattr(gateway, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(gateway.settings, "openai_api_key", "test-key")
    with pytest.raises(PrivacyViolationError):
        map_invoice_columns_with_ai(
            ["John Smith - confidential account"],
            PrivacyContext(),
        )
    assert not FakeOpenAI.instances


def test_ai_fallback_maps_original_local_values(monkeypatch):
    import app.services.private_ai_gateway as gateway

    FakeOpenAI.instances = []
    FakeOpenAI.result = AIColumnMappingResult(mappings=[
        AIColumnMapping(column_name="supplier", field_name="supplier_name",
                        confidence=0.99),
        AIColumnMapping(column_name="buyer", field_name="customer_name",
                        confidence=0.99),
        AIColumnMapping(column_name="service", field_name="description",
                        confidence=0.99),
        AIColumnMapping(column_name="total", field_name="total_amount_aed",
                        confidence=0.99),
    ])
    monkeypatch.setattr(gateway, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(gateway.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(gateway.settings, "ai_fallback_enabled", True)

    agent = DocumentIntelligenceAgent()
    source = {
        "filename": "private-account.pdf",
        "file_type": "xlsx",
        "text": "",
        "records": [],
        "tables": [{
            "sheet_name": "Register",
            "columns": [
                "Invoice Reference", "Supplier", "Buyer", "Service",
                "Supplier TRN", "Total", "Currency",
            ],
            "records": [{
                "Invoice Reference": "RAI-PRIVATE-1",
                "Supplier": "Private Supplier",
                "Buyer": "Private Buyer",
                "Service": "Confidential consulting work",
                "Supplier TRN": "100123456700003",
                "Total": "100.00",
                "Currency": "AED",
            }],
        }],
        "metadata": {"secret": "must not be sent"},
        "warnings": [],
    }
    result = agent.extract_document(source)
    assert result["processing_mode"] == "REDACTED_AI"
    assert result["ai_called"] is True
    assert result["sensitive_data_transmitted"] is False
    assert result["invoices"][0]["invoice_number"] == "RAI-PRIVATE-1"
    assert result["invoices"][0]["supplier_name"] == "Private Supplier"

    request = FakeOpenAI.instances[0].responses.calls[0]
    outbound = json.dumps(request, default=str)
    for secret in (
        "RAI-PRIVATE-1",
        "Private Supplier",
        "Private Buyer",
        "Confidential consulting work",
        "private-account.pdf",
        "must not be sent",
    ):
        assert secret not in outbound
    validate_outbound_payload(request, PrivacyContext())
