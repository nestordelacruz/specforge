"""OpenAPI spec -> schema-validated test definitions, via Claude.

This module is the only place in the pipeline that talks to an LLM. Everything
downstream consumes a validated TestSuite and is deterministic. Keeping that
boundary in one small module is the point of the architecture: when a generated
test misbehaves, there is exactly one file where non-determinism could have
entered.
"""
import json
import os
from pathlib import Path

import anthropic

from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schema import TestSuite

# Sonnet 5: strong on schema-constrained structured output at a cost that suits
# a generator run repeatedly in CI. Override with CLAUDE_MODEL.
DEFAULT_MODEL = "claude-sonnet-5"

# Generous ceiling: a full suite for a small spec is well under this, but
# truncation mid-JSON is a failure mode worth spending headroom to avoid.
MAX_TOKENS = 16000


class GenerationError(RuntimeError):
    """Raised when the model did not return a usable suite."""


def generate_suite(
    spec: dict,
    *,
    client: anthropic.Anthropic | None = None,
    model: str | None = None,
) -> TestSuite:
    """Generate a validated TestSuite from a parsed OpenAPI spec.

    The client is injectable so tests can exercise the parsing and validation
    path without a network call.
    """
    client = client or anthropic.Anthropic()
    model = model or os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)

    response = client.messages.parse(
        model=model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(json.dumps(spec, indent=2))}],
        output_format=TestSuite,
    )

    # Structured outputs guarantee the shape, not that a response arrived at
    # all. These are the two ways it can still come back unusable.
    if response.stop_reason == "refusal":
        raise GenerationError("Model declined the request; no suite was generated.")
    if response.stop_reason == "max_tokens":
        raise GenerationError(
            f"Response hit the {MAX_TOKENS}-token ceiling and was truncated. "
            "Raise MAX_TOKENS or narrow the spec."
        )

    suite = response.parsed_output
    if suite is None:
        raise GenerationError(f"No parsed suite in response (stop_reason={response.stop_reason}).")
    return suite


def load_spec(path: Path) -> dict:
    """Read an OpenAPI spec from disk."""
    return json.loads(path.read_text(encoding="utf-8"))
