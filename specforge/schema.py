"""The contract between the LLM and the rest of the pipeline.

This is the single validated boundary the architecture depends on: the model
emits structured data matching these models, and everything downstream
(rendering, execution, diagnosis) is deterministic. If it doesn't validate
here, it never reaches the deterministic half.
"""
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


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

    path_params: dict[str, str] | None = Field(
        default=None, description="Values substituted into the path template."
    )
    query_params: dict[str, str] | None = None
    body: dict | None = Field(default=None, description="JSON request body, if any.")

    expected_status: int = Field(description="The HTTP status code this request must return.")
    expected_body_contains: dict | None = Field(
        default=None,
        description="Subset of fields the response body must contain. Omit when "
        "only the status code matters.",
    )


class TestSuite(BaseModel):
    """A full generated suite, plus the spec version it was generated from."""

    model_config = ConfigDict(extra="forbid")

    spec_title: str
    spec_version: str
    tests: list[TestDefinition]
