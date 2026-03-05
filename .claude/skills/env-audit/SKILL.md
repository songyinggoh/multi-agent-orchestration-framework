---
name: env-audit
description: >
  Cross-references environment variable definitions (Zod schema, config files),
  .env.example files, and CI workflow secrets to catch env var drift whenever
  new credentials are added. Use when adding a new env var, onboarding, or
  reviewing a PR that touches config.
user-invocable: true
---

# /env-audit

Environment variable drift detector for software projects. Every env var may live in multiple places - config/validation schemas, `.env.example` files, CI workflow `env:` blocks, and cloud provider secrets. This skill audits all surfaces and reports what's missing or mismatched.

## When to Use

- **Adding a new env var**: make sure all surfaces are updated, not just the schema
- **Onboarding a new developer**: verify `.env.example` is complete enough to run locally
- **PR review**: a PR that touches config/env should always update `.env.example`
- **Rotating a secret**: identify every CI workflow job that injects the old secret
- **Feature flag**: confirm the flag is in `.env.example` with a safe default
- **CI failure "env var missing"**: quickly find which surface was skipped

## Invocation

```
/env-audit
/env-audit <var-name>       # audit a single variable across all surfaces
/env-audit --new <VAR_NAME> # generate the boilerplate for a new variable
```

**Examples**:
```
/env-audit
/env-audit DATABASE_URL
/env-audit --new SENDGRID_API_KEY
```

---

## Audit Surfaces

Detect and audit whichever of these surfaces exist in the project:

| # | Surface | Common Locations | Purpose |
|---|---------|-----------------|---------|
| 1 | **Validation schema** | `src/config/env.ts`, `env.mjs`, `.env.schema` | Runtime validation + types |
| 2 | **Backend .env.example** | `.env.example`, `backend/.env.example` | Dev onboarding reference |
| 3 | **Frontend .env.example** | `frontend/.env.example`, `.env.local.example` | Frontend env vars (e.g. `NEXT_PUBLIC_*`, `VITE_*`) |
| 4 | **CI env blocks** | `.github/workflows/*.yml`, `.gitlab-ci.yml` | Test/deploy values injected into jobs |
| 5 | **Cloud secrets** | Repo Settings / Cloud Provider | Real credentials for prod (not in files) |
| 6 | **Docker/Compose** | `docker-compose.yml`, `Dockerfile` | Container environment |

A var is **drifted** when it appears in the validation schema but is absent from one or more surfaces where it should be.

---

## Step-by-Step Audit Workflow

### 1. Discover env config files

Search the project for env-related files:
```
- Glob for *.env*, .env.example, env.ts, env.mjs, env.schema
- Check for Zod/Joi/Yup validation schemas
- Check docker-compose.yml for environment sections
```

### 2. Build the canonical variable list

Extract every env var from the validation schema. Classify each as:
- `REQUIRED` - no `.optional()` and no `.default()`
- `DEFAULTED` - has `.default(value)`
- `OPTIONAL` - `.optional()` with no default (feature-gated)

### 3. Compare against .env.example files

For every var in the schema, check if `.env.example` has an entry:
- Required vars: must appear uncommented
- Defaulted vars: should appear with the default value
- Optional vars: should appear commented out (so devs know the var exists)

### 4. Scan CI workflow files for env var usage

Read all workflow files and catalog:
- Inline values (`env:` blocks with hardcoded values) - safe stubs for tests
- Secret references (`${{ secrets.VAR_NAME }}`) - must be provisioned in repo settings

### 5. Cross-reference: does every secret-gated var have a CI secret?

For each `REQUIRED` or feature-enabling var, verify it's available in CI.

### 6. Report findings

Output a table with:
- PASS - var present in all expected surfaces
- DRIFT - var missing from one or more surfaces
- ACTION REQUIRED - required var missing from a critical surface

---

## Adding a New Env Var (Checklist)

When adding any new var, touch all relevant surfaces:

```
[ ] 1. Add to validation schema (with .optional(), .default(), or required)
[ ] 2. Add to .env.example with comment explaining purpose
[ ]    - Required vars: uncommented with example value
[ ]    - Optional vars: commented out with # prefix
[ ] 3. If frontend-specific (NEXT_PUBLIC_*, VITE_*): add to frontend .env.example
[ ] 4. If needed in CI tests: add to relevant workflow env: blocks
[ ] 5. If a real secret: add to cloud/repo secret management
[ ] 6. If using Docker: add to docker-compose.yml environment section
```

---

## Quick Reference

| Pattern | Example (Zod) |
|---------|---------------|
| Required var | `MY_KEY: z.string().min(1, 'MY_KEY is required')` |
| Optional var | `MY_KEY: z.string().optional()` |
| Defaulted var | `MY_KEY: z.string().default('value')` |
| Boolean flag | `MY_FLAG: z.enum(['true','false']).default('false').transform(v => v === 'true')` |
| Number var | `PORT: z.coerce.number().default(3000)` |
| URL var | `API_URL: z.string().url()` |
| Helper function | `export function isFeatureEnabled(): boolean { return !!env.MY_KEY; }` |
