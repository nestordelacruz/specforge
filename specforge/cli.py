"""Command line: specforge generate | render | run.

    python -m specforge.cli generate target_api/openapi.json -o suite.json
    python -m specforge.cli render   suite.json -o generated/
    python -m specforge.cli run      generated/ --base-url http://127.0.0.1:8000
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from .executor import run_suite
from .generator import GenerationError, generate_suite, load_spec
from .renderer import RenderError, render_suite
from .schema import TestSuite


def _cmd_generate(args: argparse.Namespace) -> int:
    if not args.spec.is_file():
        print(f"error: spec not found: {args.spec}", file=sys.stderr)
        return 2
    try:
        suite = generate_suite(load_spec(args.spec), model=args.model)
    except GenerationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args.out.write_text(suite.model_dump_json(indent=2), encoding="utf-8")
    print(f"Generated {len(suite.tests)} tests -> {args.out}")
    for case_type, count in sorted(Counter(t.case_type.value for t in suite.tests).items()):
        print(f"  {case_type:<15} {count}")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    if not args.suite.is_file():
        print(f"error: suite not found: {args.suite}", file=sys.stderr)
        return 2
    suite = TestSuite.model_validate_json(args.suite.read_text(encoding="utf-8"))
    try:
        files = render_suite(suite)
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    for name, source in sorted(files.items()):
        (args.out / name).write_text(source, encoding="utf-8")
    print(f"Rendered {len(suite.tests)} tests -> {args.out}/")
    for name in sorted(files):
        print(f"  {name}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        result = run_suite(args.generated, args.base_url, quiet=not args.verbose)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if result.total == 0:
        print("error: no results collected — the suite did not run", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        return 2

    counts = result.counts
    print(f"Ran {result.total} tests against {args.base_url}")
    for outcome, count in sorted(counts.items()):
        print(f"  {outcome:<10} {count}")

    if result.failures:
        print(f"\n{len(result.failures)} failing:")
        for failure in result.failures:
            print(f"  - {failure.test_id}")
        print("\nEach failure is one of: a real service bug, a bad generated test, or a")
        print("harness defect. Triage before treating any of them as noise.")
    # A failing test is a finding, not a crash — surface it via exit code so CI
    # can gate on it, but distinguish it from an executor error (2).
    return 1 if result.failures else 0


def main(argv: list[str] | None = None) -> int:
    # .env.example documents ANTHROPIC_API_KEY and CLAUDE_MODEL living in .env,
    # so the CLI has to actually read it. Real environment variables win.
    load_dotenv(override=False)

    parser = argparse.ArgumentParser(prog="specforge", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="OpenAPI spec -> validated test definitions")
    gen.add_argument("spec", type=Path, help="Path to openapi.json")
    gen.add_argument("-o", "--out", type=Path, default=Path("suite.json"))
    gen.add_argument("--model", default=None, help="Override the Claude model")
    gen.set_defaults(func=_cmd_generate)

    ren = sub.add_parser("render", help="test definitions -> runnable pytest")
    ren.add_argument("suite", type=Path, help="Path to suite.json")
    ren.add_argument("-o", "--out", type=Path, default=Path("generated"))
    ren.set_defaults(func=_cmd_render)

    run = sub.add_parser("run", help="execute a rendered suite against a live target")
    run.add_argument("generated", type=Path, help="Directory holding the rendered suite")
    run.add_argument("--base-url", default="http://127.0.0.1:8000")
    run.add_argument("-v", "--verbose", action="store_true")
    run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
