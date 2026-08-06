"""Tests for the generator boundary.

The Claude call is mocked throughout: these verify the validation and
error-handling logic around the LLM, which is the part that must be reliable.
Whether the model writes *good* tests is a question for Phase 4's flake
detection and real evaluation, not for a unit test.
"""
from types import SimpleNamespace

import pytest

from specforge.generator import GenerationError, generate_suite
from specforge.schema import Auth, CaseType, SetupStep, TestDefinition, TestSuite

VALID_TEST = TestDefinition(
    id="create_reading_valid",
    description="A valid mg/dL reading is accepted.",
    case_type=CaseType.positive,
    spec_ref="POST /readings",
    method="POST",
    path="/readings",
    auth=Auth.user,
    body='{"value": 120, "unit": "mg/dL", "trend": "rising"}',
    expected_status=201,
)


class _FakeStream:
    """Stands in for the SDK's streaming context manager."""

    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def get_final_message(self):
        return self._response


def _client(*, parsed=None, stop_reason="end_turn"):
    """A stand-in Anthropic client returning one canned response."""
    response = SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)
    return SimpleNamespace(messages=SimpleNamespace(stream=lambda **kwargs: _FakeStream(response)))


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


def test_json_payloads_parse_to_dicts():
    """The wire format is a JSON string; downstream consumers get dicts."""
    assert VALID_TEST.body_dict() == {"value": 120, "unit": "mg/dL", "trend": "rising"}
    assert VALID_TEST.path_params_dict() is None


def test_malformed_json_rejected():
    """Second half of the boundary: the string must actually be usable."""
    with pytest.raises(ValueError, match="not valid JSON"):
        VALID_TEST.model_copy(update={"body": "{not json"}).model_validate(
            VALID_TEST.model_dump() | {"body": "{not json"}
        )


def test_non_object_json_rejected():
    with pytest.raises(ValueError, match="must be a JSON object"):
        TestDefinition.model_validate(VALID_TEST.model_dump() | {"body": "[1, 2, 3]"})


def test_resolved_path_substitutes_params():
    """Guards the empty-payload bug: a templated path must come out concrete."""
    t = TestDefinition.model_validate(
        VALID_TEST.model_dump()
        | {
            "path": "/readings/{reading_id}",
            "path_params": '{"reading_id": "7"}',
            "method": "GET",
            "body": None,
        }
    )
    assert t.resolved_path() == "/readings/7"
    assert "{" not in t.resolved_path()


def test_setup_step_validates_its_body():
    """Setup bodies go through the same JSON-object gate as test bodies."""
    with pytest.raises(ValueError, match="not valid JSON"):
        SetupStep(method="POST", path="/readings", auth=Auth.user, body="{nope")


def test_setup_defaults_to_empty():
    """Most tests need no setup; the field shouldn't be required."""
    assert VALID_TEST.setup == []
    assert VALID_TEST.bound_params() == set()


def test_bound_params_reports_setup_bindings():
    t = TestDefinition.model_validate(
        VALID_TEST.model_dump()
        | {
            "path": "/readings/{reading_id}",
            "setup": [
                {
                    "method": "POST",
                    "path": "/readings",
                    "auth": "user",
                    "body": '{"value": 120, "unit": "mg/dL", "trend": "steady"}',
                    "capture": "id",
                    "bind_to": "reading_id",
                }
            ],
        }
    )
    assert t.bound_params() == {"reading_id"}
    # A bound parameter stays templated — its value isn't known until run time.
    assert t.resolved_path() == "/readings/{reading_id}"


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
