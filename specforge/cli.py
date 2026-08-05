"""Command-line entry point: python -m specforge.cli <spec> [-o out.json]"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from .generator import GenerationError, generate_suite, load_spec


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="specforge",
        description="Generate schema-validated API test definitions from an OpenAPI spec.",
    )
    parser.add_argument("spec", type=Path, help="Path to openapi.json")
    parser.add_argument(
        "-o", "--out", type=Path, default=Path("suite.json"), help="Where to write the suite"
    )
    parser.add_argument("--model", default=None, help="Override the Claude model")
    args = parser.parse_args(argv)

    if not args.spec.is_file():
        print(f"error: spec not found: {args.spec}", file=sys.stderr)
        return 2

    try:
        suite = generate_suite(load_spec(args.spec), model=args.model)
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args.out.write_text(suite.model_dump_json(indent=2), encoding="utf-8")

    by_type = Counter(t.case_type.value for t in suite.tests)
    print(f"Generated {len(suite.tests)} tests -> {args.out}")
    for case_type, count in sorted(by_type.items()):
        print(f"  {case_type:<15} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
