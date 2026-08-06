"""The contract between the LLM and the rest of the pipeline.

This is the single validated boundary the architecture depends on: the model
emits structured data matching these models, and everything downstream
(rendering, execution, diagnosis) is deterministic. If it doesn't validate
here, it never reaches the deterministic half.
"""
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CaseType(str, Enum):
    """What kind of scenario a test exercises. Drives coverage reporting."""

    positive = "positive"
    negative = "negative"
    boundary = "boundary"
    authorization = "authorization"


class ContentType(str, Enum):
    """How the request body is encoded.

    Most endpoints take JSON, but OAuth2 token endpoints take form data, and
    sending one where the other is expected returns 422 — a failure that looks
    like a service bug and isn't. The spec says which under
    `requestBody.content`, so the generator can read it.
    """

    json = "json"
    form = "form"


class Auth(str, Enum):
    """Which identity issues the request.

    The executor maps these to real credentials; the generator only has to
    reason about roles, not tokens.
    """

    none = "none"
    user = "user"
    other_user = "other_user"
    admin = "admin"


def _validate_json_object(v: str | None) -> str | None:
    """Reject anything that isn't a parseable JSON object.

    This is the second half of the validated boundary: the API guarantees the
    field is a string, and this guarantees the string is usable.
    """
    if v is None:
        return v
    try:
        parsed = json.loads(v)
    except json.JSONDecodeError as exc:
        raise ValueError(f"not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        # ValueError, not TypeError: Pydantic only wraps ValueError and
        # AssertionError into ValidationError. A TypeError would escape.
        raise ValueError(f"must be a JSON object, got {type(parsed).__name__}")  # noqa: TRY004
    return v


def _load(v: str | None) -> dict[str, Any] | None:
    return json.loads(v) if v else None


class SetupStep(BaseModel):
    """A request made before the test, to create state the test depends on.

    This is what makes tests order-independent. Without it, a test targeting
    /readings/{reading_id} has to assume some row already exists — which is
    false on a fresh database, and false again after another test deletes it.
    Phase 4 measures flakiness by re-running the suite, so a test whose result
    depends on execution order would register as flaky when the service is
    perfectly stable. Isolation here is what makes that measurement mean
    anything.
    """

    model_config = ConfigDict(extra="forbid")

    method: str = Field(description="HTTP method, uppercase.")
    path: str = Field(description="Path to call, with no template parameters remaining.")
    auth: Auth = Field(description="Which identity makes this setup request.")
    content_type: ContentType = Field(
        default=ContentType.json, description="How to encode the body."
    )
    body: str | None = Field(
        default=None, description='JSON object request body, e.g. {"value": 120, "unit": "mg/dL"}.'
    )
    capture: str | None = Field(
        default=None,
        description="Field to read from this response's JSON body, e.g. 'id'. Omit "
        "if nothing needs to be carried into the test.",
    )
    bind_to: str | None = Field(
        default=None,
        description="Name of the path parameter the captured value fills, e.g. "
        "'reading_id'. Required whenever `capture` is set.",
    )

    _check_body = field_validator("body")(_validate_json_object)

    def body_dict(self) -> dict[str, Any] | None:
        return _load(self.body)


class TestDefinition(BaseModel):
    """One test case: a request to make and the response to expect."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="Stable snake_case identifier, unique within the suite.")
    description: str = Field(description="One line on what this case verifies and why.")
    case_type: CaseType
    # Traceability: which part of the spec motivated this test. This is what
    # makes the Phase 6 requirements matrix possible, so it is required rather
    # than optional — a test that can't be traced back doesn't earn its place.
    spec_ref: str = Field(
        description="The OpenAPI element this test covers, e.g. 'POST /readings' "
        "or 'components.schemas.ReadingCreate.value'."
    )

    method: str = Field(description="HTTP method, uppercase, e.g. GET or POST.")
    path: str = Field(
        description="Path template as it appears in the spec, e.g. /readings/{reading_id}."
    )
    auth: Auth = Field(description="Which identity issues the request.")

    setup: list[SetupStep] = Field(
        default_factory=list,
        description="Requests to make before this test so it does not depend on "
        "pre-existing data. A test targeting a resource by id must create that "
        "resource here and bind its id, rather than assuming one exists.",
    )

    # These four are JSON *strings*, not dicts, and that is deliberate.
    #
    # A free-form `dict` renders as an object schema with no properties, which
    # structured outputs cannot populate — the model is constrained to emit an
    # empty object every time. (Observed: 47/47 generated tests had empty
    # bodies.) Passing JSON as a string moves the free-form part behind an
    # explicit parse step, which the validators below perform at construction.
    # The boundary stays validated; it just validates in two stages instead of
    # one. Use the `*_dict` accessors downstream rather than parsing by hand.
    path_params: str | None = Field(
        default=None,
        description='JSON object of values substituted into the path template, '
        'e.g. {"reading_id": "1"}. Omit when the path has no parameters.',
    )
    query_params: str | None = Field(
        default=None,
        description='JSON object of query-string parameters, e.g. {"limit": "50"}.',
    )
    body: str | None = Field(
        default=None,
        description='The request body, always written as a JSON object, e.g. '
        '{"value": 120, "unit": "mg/dL"}. `content_type` controls only how it is '
        "encoded on the wire, so a form-encoded request still writes its fields "
        "here — a form endpoint with no body sends no credentials and fails. "
        "Omit only for requests that genuinely have no body, such as GET.",
    )

    content_type: ContentType = Field(
        default=ContentType.json,
        description="How to encode the body. Use 'form' when the spec lists "
        "application/x-www-form-urlencoded under requestBody.content — OAuth2 "
        "token endpoints do. Sending JSON there returns 422.",
    )

    expected_status: int = Field(description="The HTTP status code this request must return.")
    expected_body_contains: str | None = Field(
        default=None,
        description="JSON object of fields the response body must contain. Omit "
        "when only the status code matters.",
    )

    _check_payloads = field_validator(
        "path_params", "query_params", "body", "expected_body_contains"
    )(_validate_json_object)

    def body_dict(self) -> dict[str, Any] | None:
        return _load(self.body)

    def path_params_dict(self) -> dict[str, Any] | None:
        return _load(self.path_params)

    def query_params_dict(self) -> dict[str, Any] | None:
        return _load(self.query_params)

    def expected_body_dict(self) -> dict[str, Any] | None:
        return _load(self.expected_body_contains)

    def bound_params(self) -> set[str]:
        """Path parameters supplied by a setup step rather than a literal."""
        return {s.bind_to for s in self.setup if s.bind_to}

    def resolved_path(self) -> str:
        """The path with literal template parameters substituted.

        Parameters bound by a setup step are left as templates — their values
        aren't known until the setup request runs. A binding always wins over a
        literal for the same parameter: the captured id is a real resource,
        whereas the literal is at best a guess and at worst a placeholder the
        model invented (an observed case: path_params of "__from_setup__"
        alongside a setup step that binds the same key).
        """
        bound = self.bound_params()
        path = self.path
        for key, value in (self.path_params_dict() or {}).items():
            if key in bound:
                continue
            path = path.replace("{" + key + "}", str(value))
        return path


class TestSuite(BaseModel):
    """A full generated suite, plus the spec version it was generated from."""

    model_config = ConfigDict(extra="forbid")

    spec_title: str
    spec_version: str
    tests: list[TestDefinition]
