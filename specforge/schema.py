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


class Auth(str, Enum):
    """Which identity issues the request.

    The executor maps these to real credentials; the generator only has to
    reason about roles, not tokens.
    """

    none = "none"
    user = "user"
    other_user = "other_user"
    admin = "admin"


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
    path: str = Field(description="Path template as it appears in the spec, e.g. /readings/{reading_id}.")
    auth: Auth = Field(description="Which identity issues the request.")

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
        description='JSON object request body, e.g. {"value": 120, "unit": "mg/dL"}. '
        "Omit for requests without a body.",
    )

    expected_status: int = Field(description="The HTTP status code this request must return.")
    expected_body_contains: str | None = Field(
        default=None,
        description="JSON object of fields the response body must contain. Omit "
        "when only the status code matters.",
    )

    @field_validator("path_params", "query_params", "body", "expected_body_contains")
    @classmethod
    def _must_be_json_object(cls, v: str | None) -> str | None:
        """Reject anything that isn't a parseable JSON object.

        This is the second half of the validated boundary: the API guarantees a
        string, and this guarantees the string is usable.
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
            raise ValueError(  # noqa: TRY004
                f"must be a JSON object, got {type(parsed).__name__}"
            )
        return v

    @staticmethod
    def _load(v: str | None) -> dict[str, Any] | None:
        return json.loads(v) if v else None

    def body_dict(self) -> dict[str, Any] | None:
        return self._load(self.body)

    def path_params_dict(self) -> dict[str, Any] | None:
        return self._load(self.path_params)

    def query_params_dict(self) -> dict[str, Any] | None:
        return self._load(self.query_params)

    def expected_body_dict(self) -> dict[str, Any] | None:
        return self._load(self.expected_body_contains)

    def resolved_path(self) -> str:
        """The path with template parameters substituted, ready to request."""
        path = self.path
        for key, value in (self.path_params_dict() or {}).items():
            path = path.replace("{" + key + "}", str(value))
        return path


class TestSuite(BaseModel):
    """A full generated suite, plus the spec version it was generated from."""

    model_config = ConfigDict(extra="forbid")

    spec_title: str
    spec_version: str
    tests: list[TestDefinition]
