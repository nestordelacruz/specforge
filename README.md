# SpecForge
 
**Generates, executes, and diagnoses API test suites from an OpenAPI spec — using an LLM as the test designer and a deterministic pipeline as the referee.**
 
[![CI](https://github.com/nestordelacruz/specforge/actions/workflows/ci.yml/badge.svg)](https://github.com/nestordelacruz/specforge/actions/workflows/ci.yml)
 
---
 
## What it does
 
SpecForge takes an OpenAPI specification and produces a runnable pytest suite covering positive, negative, boundary, and authorization cases. It then executes that suite repeatedly in CI, identifies tests whose results are non-deterministic, and clusters failures into likely root causes.
 
The interesting part is not the generation. It is everything downstream of it: validating that an LLM's output is structurally sound, measuring whether the generated tests are actually stable, and turning a wall of failures into a short list of probable causes.
 
## Why this exists
 
Most AI-for-testing demos stop at "the model wrote some tests." That is the easy half. In practice the hard problems are:
 
- **Non-determinism.** An LLM asked the same question twice may answer differently. A test suite that changes between runs is worthless as a regression gate.
- **Flakiness attribution.** When a test fails intermittently, is the test wrong, the service wrong, or the environment wrong? Teams burn enormous time here.
- **Traceability.** In regulated environments, "we have tests" is insufficient. You must show which requirement each test covers.
SpecForge is built around those three problems rather than around the generation step.
 
---
 
## Architecture
 
```
OpenAPI spec
     │
     ▼
┌─────────────────┐   temperature 0 + strict JSON schema validation
│  Generator      │   ──────────────────────────────────────────────
│  (Claude API)   │   emits structured test definitions, not raw code
└────────┬────────┘
         ▼
┌─────────────────┐   deterministic templating: definitions ──> pytest
│  Renderer       │
└────────┬────────┘
         ▼
┌─────────────────┐   runs against a controlled FastAPI service
│  Executor       │   schema validation + business-rule assertions
└────────┬────────┘
         ▼
┌─────────────────┐   N repeated runs in CI
│  Flake Detector │   classifies stable / flaky / consistently failing
└────────┬────────┘
         ▼
┌─────────────────┐   LLM clusters failures into probable root causes
│  Diagnostics    │   + maps tests back to spec requirements
└─────────────────┘
```
 
### Design decisions
 
<!-- These are the sections hiring managers actually read. Expand them as you build;
     each one is a chance to show reasoning rather than tool familiarity. -->
 
**The system under test is my own service, not a public API.**
A controlled target lets me design schemas with deliberately tricky validation, plant a known-flaky endpoint to prove the detector works, and run fully offline with no rate limits or third-party nondeterminism. A public API would make every failure ambiguous.
 
**The LLM emits structured data, not code.**
Generation returns JSON test definitions validated against a strict schema. Rendering to pytest is deterministic templating. This keeps the non-deterministic component confined to one boundary that can be validated, rather than letting it produce arbitrary executable output.
 
**A strict schema on every generation call — not a temperature setting.**
This started out as "temperature 0 + schema validation." The temperature half no longer exists: sampling parameters were removed on current Claude models, and even where they were still accepted they never actually guaranteed identical output. So the structural guarantee rests entirely on the schema. Generation uses structured outputs — the API constrains the response to a strict JSON schema — so malformed output isn't a case the pipeline has to handle; it can't reach it. What remains are two narrow failure modes, both handled explicitly in `specforge/generator.py`: the model declining the request, and a response hitting the token ceiling mid-suite.

The deeper point: *structural* determinism (the output is always a valid test definition) is guaranteed, while *semantic* stability (the same spec producing the same tests run over run) is not — it is measured, by the flake detector in Phase 4. Assuming that stability rather than measuring it is exactly the mistake this project exists to avoid.
 
**Flakiness is measured, not assumed.**
<!-- TODO: describe your N-run strategy and the threshold you chose for calling a test flaky,
     and why. -->
 
**Requirements traceability is a first-class feature.**
Each generated test carries a reference back to the spec element that motivated it, producing a coverage matrix. This comes directly from working in FDA-regulated medical device software, where design controls require demonstrable requirement-to-test linkage.
 
---
 
## Quickstart
 
```bash
git clone https://github.com/nestordelacruz/specforge.git
cd specforge
 
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
 
cp .env.example .env             # then add your Anthropic API key
 
uvicorn app.main:app --reload    # target service at http://127.0.0.1:8000
```
 
Interactive API docs: `http://127.0.0.1:8000/docs`
OpenAPI spec: `http://127.0.0.1:8000/openapi.json`
 
Run the service's own tests:
 
```bash
pytest
```
 
---
 
## Project structure
 
<!-- TODO: adjust to match your actual layout. -->
 
```
specforge/
├── target_api/           # FastAPI target service (system under test)
│   ├── app/              # main, models, schemas, security, routers/
│   ├── tests/            # the target's own suite
│   ├── openapi.json      # the contract the generator consumes
│   └── requirements.txt  # pinned; separate from the tool's deps
├── specforge/            # the tool itself
│   ├── schema.py         # the validated LLM boundary (TestDefinition/TestSuite)
│   ├── prompts.py        # generation prompt, isolated for review
│   ├── generator.py      # OpenAPI spec ──> structured test definitions
│   ├── cli.py            # python -m specforge.cli <spec> -o suite.json
│   ├── renderer.py       # (Phase 3) definitions ──> pytest files
│   ├── executor.py       # (Phase 3) runs suites, collects results
│   └── analysis.py       # (Phase 4/5) flake detection + failure clustering
├── tests/                # the tool's own tests (Claude call mocked)
├── .github/workflows/
└── requirements.txt      # tool deps only
```

The two packages are deliberately separate deployables: `target_api` is the
service under test, `specforge` is the tool that tests it, and the only thing
crossing between them is `openapi.json` — an observable contract, not shared
source. They have their own dependency sets and their own CI jobs.

## Usage

```bash
python -m specforge.cli target_api/openapi.json -o suite.json
```

Requires `ANTHROPIC_API_KEY`. Prints a per-case-type breakdown and writes the
validated suite to `suite.json`.
 
## Roadmap
 
- [x] **Phase 1** — Target FastAPI service: auth, CRUD resource, complex validation, permission enforcement
- [x] **Phase 2** — Generator: OpenAPI spec to schema-validated test definitions via Claude
- [ ] **Phase 3** — Renderer and executor: definitions to runnable pytest, executed against the target
- [ ] **Phase 4** — Flake detection across N CI runs
- [ ] **Phase 5** — LLM failure clustering and root-cause summaries
- [ ] **Phase 6** — Requirements traceability matrix
- [ ] **Phase 7** — Dashboard
## Tech stack
 
Python · FastAPI · pytest · SQLite · Pydantic · Anthropic API · Docker · GitHub Actions
 
---
 
## Notes
 
This is a personal project. The target service uses synthetic data and a schema of my own design; it is not derived from any employer system.