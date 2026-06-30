# Apidiom release-readiness code review

Base: `HEAD`

Scope: all tracked staged and unstaged changes plus untracked `CONTEXT.md` and `scripts/pack-smoke.cjs`.

## Findings

### CRITICAL

None.

### HIGH

1. `ts/generate/mcp.ts:74` — Upstream HTTP failures are not comprehensively converted to MCP errors.

   `_request` rejects only status codes `>= 400` (`ts/generate/mcp.ts:80`). A 3xx response is therefore returned as a successful tool result even though the generated server does not follow the redirect. The response stream also has no `error`/premature-abort handler, so a connection reset after headers can leave the promise unsettled or raise an unhandled stream error instead of returning an MCP result with `isError: true`. This violates the explicit upstream-failure requirement despite the new 404 test passing.

   Concrete fix: define success as 2xx (or implement a bounded redirect policy and then require a final 2xx), reject other final statuses, and attach response-stream failure handling. Add parsed JSON-RPC integration coverage for a redirect and a response aborted after headers, asserting the response for the matching request ID has `result.isError === true`.

2. `scripts/pack-smoke.cjs:35` — The release “pack smoke” never runs the packed CLI or validates the packed `bin` mapping.

   It hard-codes `package/dist/cli.js`, regexes its source for a `version:` literal, and prints `Packed CLI version OK`. It can pass when `packedPackage.bin.apidiom` points to a missing/wrong file, when the packed executable fails at startup, or when runtime metadata/module resolution is broken. This is source inspection, not a package smoke test, and creates false confidence immediately before publish.

   Concrete fix: resolve the executable from the packed package's `bin.apidiom`, execute that packed artifact with `--version` (ideally through an installation of the tarball), and require exit code 0, empty error output, and exact version output. Prefer npm/a maintained tar implementation over the partial hand-written tar parser at `scripts/pack-smoke.cjs:48`.

### MEDIUM

1. `package.json:2` — Published metadata omits the license even though the repository and packed tarball declare MIT through `LICENSE` and README.

   npm metadata therefore does not explicitly identify this open-source package as MIT. Concrete fix: add `"license": "MIT"` and regenerate the root package-lock metadata.

2. `ts/generate/mcp.ts:195` — The touched production module is 340 pure LOC and owns HTTP transport generation, tool generation, and two largely parallel MCP protocol handlers (`ts/generate/mcp.ts:252`). It was already oversized at HEAD (325 pure LOC), and this diff adds another 15 pure lines.

   This violates the consulted programming/remove-ai-slops 250-pure-LOC perspective and keeps error translation duplicated across flat and search modes. Concrete fix: split by responsibility, with shared MCP tool-call/error-result generation used by both modes; do not add generic helpers without a second caller.

3. `ts-tests/cli.test.ts:99` — The expanded integration test conflates tool listing, three successful calls, header forwarding, and HTTP failure into one scenario, then asserts unrelated global stdout substrings at `ts-tests/cli.test.ts:161`. The new search-mode test at `ts-tests/cli.test.ts:219` duplicates roughly the same server/process lifecycle.

   The error assertions can pass without proving that request ID 6 is the response carrying `isError`, and the duplicated lifecycle increases maintenance cost; the file is now 409 pure LOC. Concrete fix: extract a narrowly typed MCP process harness, parse each JSON line, correlate responses by ID, and keep one observable outcome per test.

### LOW

1. `ts-tests/ingest/parse.test.ts:50` — The new path-item parameter test covers inheritance but not the OpenAPI rule that an operation-level parameter with the same `(in, name)` overrides the path-item parameter. `mergeParameters` depends on concatenation order for that behavior (`ts/ingest/parse.ts:83`). Add an override case so a future reorder cannot silently break the contract.

2. The intended release set is split across staged, unstaged, and untracked state. In particular, the release-version guard and HTTP-status fix are unstaged, `package-lock.json` is unstaged, and `scripts/pack-smoke.cjs`/`CONTEXT.md` are untracked. The aggregate worktree was reviewed and tested, but the current index alone is not release-ready. Stage the complete intended set together before the user commits.

## Requirement assessment

- TypeScript-first: PASS. Runtime behavior remains under `ts/`; the CommonJS smoke helper is release tooling.
- Preserve `archive/python` quarantine: PASS. `git diff HEAD -- archive/python` is empty.
- Remove only proven-unused artifacts: PASS for `docs/inspect-tmp.mjs`. It has no repository references, was a hard-coded local Playwright probe, and its only history is its original addition.
- Generated MCP surfaces upstream HTTP failures as MCP errors: FAIL. 4xx/5xx and request-level errors are translated, but redirect and response-stream failure paths remain.
- Release workflow runs build/typecheck/test/pack-smoke before publish: PASS for ordering at `.github/workflows/release.yml:26`; FAIL for the smoke gate's substance as described above.
- Package metadata coherent: PARTIAL. Package/lock/embedded CLI versions are 0.4.0 and the bin artifact is packed, but license metadata is missing and the smoke does not validate `bin`.
- No publish or push: PASS. Neither was performed during review.

## Independent verification

- `npm run build`: PASS; generated `dist/cli.js`.
- `npm run typecheck`: PASS.
- `npm test`: PASS; 8 files, 94 tests.
- `npm run pack:smoke`: PASS as currently implemented; output `Packed CLI version OK: 0.4.0` is not sufficient to clear HIGH finding 2.
- `npm pack --dry-run --json`: PASS; tarball contains `LICENSE`, `README.md`, `dist/cli.js`, and `package.json`.
- `git diff --check HEAD`: PASS (line-ending conversion warnings only).

No prior evidence paths or notepad path were provided, and `.omo` did not exist before this review. All evidence above was independently inspected or executed.

## Skill-perspective check

The full `omo:remove-ai-slops` and `omo:programming` skills, the TypeScript README, and TypeScript error-handling reference were consulted before maintainability/test judgment. The bundled automated TypeScript no-excuse checker could not run because Bun is not installed; the rules were applied manually.

- `remove-ai-slops`: VIOLATED by the partial hand-written tar extraction/source-regex smoke, the oversized touched modules, and duplicated/broad integration scenario. No deletion-only, tautological, or “requested removal” tests were added.
- `programming`: VIOLATED by the oversized production/test modules and global-string protocol assertions rather than parsed, request-correlated outcomes. No new production `any`, `@ts-ignore`, `@ts-expect-error`, or non-null assertion was found.

## Decision

- `codeQualityStatus`: `BLOCK`
- `recommendation`: `REQUEST_CHANGES`
- `reportPath`: `.omo/evidence/apidiom-release-readiness-code-review.md`
- `blockers`:
  - Handle all non-success HTTP/stream failure paths as MCP errors and cover them with request-correlated protocol tests.
  - Make pack-smoke execute and validate the packed package's declared CLI bin rather than regexing source text.

Merge readiness: NOT READY.
