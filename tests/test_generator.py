"""Tests for the generator boundary.

The Claude call is mocked throughout: these verify the validation and
error-handling logic around the LLM, which is the part that must be reliable.
Whether the model writes *good* tests is a question for Phase 4's flake
detection and real evaluation, not for a unit test.
"""
from types import SimpleNamespace

import pytest

from specforge.generator import GenerationError, generate_suite
from specforge.schema import Auth, CaseType, TestDefinition, TestSuite

VALID_TEST = TestDefinition(
    id="create_reading_valid",
    description="A valid mg/dL reading is accepted.",
    case_type=CaseType.positive,
    spec_ref="POST /readings",
    method="POST",
    path="/readings",
    auth=Auth.user,
    body={"value": 120, "unit": "mg/dL", "trend": "rising"},
    expected_status=201,
)


def _client(*, parsed=None, stop_reason="end_turn"):
    """A stand-in Anthropic client returning one canned response."""
    response = SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)
    return SimpleNamespace(messages=SimpleNamespace(parse=lambda **kwargs: response))


def test_returns_validated_suite():
    suite = TestSuite(spec_title="SpecForge Target API", spec_version="0.1.0", tests=[VALID_TEST])
    result = generate_suite({}, client=_client(parsed=suite))
    assert result.tests[0].id == "create_reading_valid"
    assert result.tests[0].case_type is CaseType.positive


def test_refusal_raises():
    with pytest.raises(GenerationError, match="declined"):
        generate_suite({}, client=_client(stop_reason="refusal"))


def test_truncation_raises():
    with pytest.raises(GenerationError, match="truncated"):
        generate_suite({}, client=_client(stop_reason="max_tokens"))


def test_missing_suite_raises():
    with pytest.raises(GenerationError, match="No parsed suite"):
        generate_suite({}, client=_client(parsed=None))


def test_spec_ref_is_required():
    """Traceability is a schema-level guarantee, not a convention."""
    with pytest.raises(ValueError):
        TestDefinition(
            id="x",
            description="missing spec_ref",
            case_type=CaseType.positive,
            method="GET",
            path="/readings",
            auth=Auth.user,
            expected_status=200,
        )


def test_unknown_fields_rejected():
    """extra='forbid' keeps model drift from silently entering the pipeline."""
    with pytest.raises(ValueError):
        TestDefinition(
            id="x",
            description="has an unexpected field",
            case_type=CaseType.positive,
            spec_ref="GET /readings",
            method="GET",
            path="/readings",
            auth=Auth.user,
            expected_status=200,
            invented_field="surprise",
        )
