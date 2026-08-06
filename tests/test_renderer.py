"""Tests for the renderer.

The renderer is a pure function, so all of this runs offline with no target
service and no LLM. What's verified here is the property the design depends on:
that rendering is deterministic and that setup steps produce order-independent
tests. Those two things are what make the Phase 4 flake measurement meaningful,
so they get real tests rather than being assumed.
"""
import ast

import pytest

from specforge.renderer import RenderError, render_suite, render_test
from specforge.schema import Auth, CaseType, ContentType, SetupStep, TestDefinition, TestSuite


def _test_def(**overrides) -> TestDefinition:
    base = {
        "id": "create_reading_valid",
        "description": "A valid mg/dL reading is accepted.",
        "case_type": CaseType.positive,
        "spec_ref": "POST /readings",
        "method": "POST",
        "path": "/readings",
        "auth": Auth.user,
        "body": '{"value": 120, "unit": "mg/dL", "trend": "rising"}',
        "expected_status": 201,
    }
    return TestDefinition(**{**base, **overrides})


OWNED_READING = SetupStep(
    method="POST",
    path="/readings",
    auth=Auth.user,
    body='{"value": 120, "unit": "mg/dL", "trend": "steady"}',
    capture="id",
    bind_to="reading_id",
)


def _suite(*tests) -> TestSuite:
    return TestSuite(spec_title="SpecForge Target API", spec_version="0.1.0", tests=list(tests))


def test_rendered_files_are_valid_python():
    files = render_suite(_suite(_test_def()))
    for source in files.values():
        ast.parse(source)


def test_render_is_deterministic():
    """Rendered output is committed, so an unchanged suite must produce an
    unchanged file — otherwise the git diff stops being a stability signal."""
    suite = _suite(_test_def(), _test_def(id="another", path="/readings", expected_status=201))
    assert render_suite(suite) == render_suite(suite)


def test_tests_are_sorted_by_id():
    """Ordering comes from the ids, not from the model's output order, so a
    reshuffled suite doesn't show up as a diff."""
    src = render_suite(_suite(_test_def(id="zebra"), _test_def(id="alpha")))["test_suite.py"]
    assert src.index("def test_alpha") < src.index("def test_zebra")


def test_spec_ref_reaches_the_docstring():
    """Traceability has to survive rendering — this is the Phase 6 link."""
    src = render_test(_test_def(spec_ref="components.schemas.ReadingCreate.value"))
    assert "components.schemas.ReadingCreate.value" in src
    assert ast.get_docstring(ast.parse(src).body[0]) is not None


def test_setup_step_creates_and_binds():
    """The isolation mechanism: create the resource, capture its id, use it."""
    src = render_test(
        _test_def(
            id="other_user_denied",
            case_type=CaseType.authorization,
            method="GET",
            path="/readings/{reading_id}",
            auth=Auth.other_user,
            body=None,
            expected_status=403,
            setup=[OWNED_READING],
        )
    )
    ast.parse(src)
    # Created as the owner...
    assert 'clients["user"].post("/readings"' in src
    assert 'reading_id = _setup0.json()["id"]' in src
    # ...and requested as somebody else, using the captured id.
    assert 'clients["other_user"].get(f"/readings/{reading_id}")' in src
    # No literal id anywhere — that's the whole point.
    assert "/readings/1" not in src


def test_literal_path_param_is_substituted():
    """Deliberate not-found cases still use a literal, and shouldn't become f-strings."""
    src = render_test(
        _test_def(
            id="missing_reading",
            method="GET",
            path="/readings/{reading_id}",
            auth=Auth.user,
            body=None,
            path_params='{"reading_id": "999999"}',
            expected_status=404,
        )
    )
    ast.parse(src)
    assert 'get("/readings/999999")' in src


def test_unfilled_path_param_raises():
    """A path parameter with no literal and no binding fails loudly at render
    time rather than producing a request to a URL with a brace in it."""
    with pytest.raises(RenderError, match="reading_id"):
        render_test(
            _test_def(
                id="broken",
                method="GET",
                path="/readings/{reading_id}",
                auth=Auth.user,
                body=None,
            )
        )


def test_setup_binding_beats_a_literal_path_param():
    """Observed in a real run: the model supplied both a setup binding and a
    placeholder literal ("__from_setup__") for the same parameter. The captured
    id must win, or the request goes to a URL built from the placeholder."""
    src = render_test(
        _test_def(
            id="binding_wins",
            method="GET",
            path="/readings/{reading_id}",
            auth=Auth.user,
            body=None,
            path_params='{"reading_id": "__from_setup__"}',
            expected_status=200,
            setup=[OWNED_READING],
        )
    )
    ast.parse(src)
    assert "__from_setup__" not in src
    assert 'get(f"/readings/{reading_id}")' in src


def test_expected_body_becomes_assertions():
    """Works for both an object response and a list response — GET /readings
    returns an array, and indexing a list by field name is a TypeError."""
    src = render_test(_test_def(expected_body_contains='{"unit": "mg/dL"}'))
    ast.parse(src)
    assert "isinstance(payload, list)" in src
    assert 'any(item.get("unit") == "mg/dL" for item in items)' in src


def test_form_content_type_uses_data_keyword():
    """OAuth2 token endpoints take form encoding; sending JSON returns 422."""
    src = render_test(
        _test_def(
            id="token_exchange",
            path="/auth/token",
            content_type=ContentType.form,
            body='{"username": "a@example.com", "password": "password123"}',
            expected_status=200,
        )
    )
    ast.parse(src)
    assert "data={" in src
    assert "json={" not in src


def test_conftest_defines_every_role():
    conftest = render_suite(_suite(_test_def()))["conftest.py"]
    ast.parse(conftest)
    for role in ("none", "user", "other_user", "admin"):
        assert f'"{role}"' in conftest
