# MigraDiff — Project Plan

**Project:** MigraDiff (fork of djrobstep/migra)
**Package:** `migradiff` (PyPI) · CLI command: `migra`
**License:** MIT
**Repository:** https://github.com/migradiff/migra
**Maintainer:** Leo (Roongrunchai Chongolnee) · leo@lateos.ai
**Parent company:** Lateos (lateos.ai)
**Current version:** 1.4.0
**Last updated:** June 1, 2026

---

## 1. Executive Summary

MigraDiff is the actively maintained fork of `djrobstep/migra`, the
PostgreSQL schema diff tool deprecated in 2024. It compares two
PostgreSQL schemas and generates the SQL migration script needed to
transform one into the other.

The fork fixes known upstream issues, adds Python 3.12+ support, and
extends the tool with a complete AI-powered migration assistant suite
(explain, rollback, advise, generate). The CLI command remains `migra`
for backward compatibility; the PyPI package is `migradiff`.

MigraDiff is positioned for acquisition by Supabase or Redgate within
2–3 years at $10–20M, built on $1–2M ARR from 200–300 paying customers.

---

## 2. Current State (v1.4.0)

- 175 tests passing, 2 skipped, 0 failing
- flake8: 0 warnings
- black: clean
- Python 3.10+ required, PostgreSQL 12+
- Docker image: `ghcr.io/migradiff/migra`
- GitHub Action: `migradiff/migra-action`
- Pre-commit hook available
- AI features: `pip install migradiff[ai]` (optional, uses user's
  own Anthropic API key — no MigraDiff infrastructure required)

### Shipped Features

**Core diff engine (inherited + improved):**
- Tables, columns, constraints, indexes
- Views and materialized views
- Functions and stored procedures
- Sequences, enums, composite types, domains
- Row-Level Security (RLS) policies (fixed from upstream)
- Foreign data wrappers
- Column-level privileges
- Partitioned tables

**Fork additions (deterministic):**
- `--from-file` — diff pg_dump schema files, no live connection needed
- `--from-migrations-dir` — diff against a migrations folder
  (Supabase, Flyway, numeric naming)
- `--schema` — comma-separated, cross-schema dependency resolution
- `--output json` — per-statement risk classification
- `--unsafe` — include destructive operations in output
- Python 3.12+ clean (no deprecation warnings)
- Actionable error messages with object name and issue link
- Docker image and GitHub Action
- Pre-commit hook
- Docker Compose dev environment

**Fork additions (AI suite — v1.3.0–v1.4.0):**
- `--explain` — plain-English migration explanation with risk analysis
- `--rollback` — generates reversal migration SQL
- `--advise` — deterministic + AI performance/risk assessment
- `--generate` — writes migration SQL from plain-English description,
  grounded in real schema from live connection or schema file

**AI safety rules (`--generate`):**
- Hard refuse on bulk destructive descriptions: "drop all", "delete all",
  "truncate all", "drop everything", "wipe"
- Soft warn on individual destructive operations: "drop", "delete",
  "truncate", "remove table", "remove column"
- All AI output marked as AI-generated in header
- Temperature 0 for determinism (Claude Haiku)
- Combinable with `--advise` for immediate deterministic risk feedback

---

## 3. Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| Database | PostgreSQL 12+ |
| AI model | Claude Haiku (Anthropic) via `anthropic` package |
| AI dependency | Optional (`migradiff[ai]`), lazy import |
| Distribution | PyPI (`migradiff`), Docker (`ghcr.io/migradiff/migra`) |
| CI | GitHub Actions (`migradiff/migra-action`) |
| Testing | pytest |
| Linting | flake8, black |
| Dev environment | Docker Compose (Postgres 16, trust auth, localhost:5432) |

---

## 4. Development Session History

Each session follows a tests-first methodology: confirm runtime failures
before implementation, no vibe-coding, explicit stop conditions, flake8
and black clean on exit.

| Session | Branch | Feature | Tests | Version |
|---|---|---|---|---|
| 001–008 | Various | Fork setup, upstream fixes, RLS, --from-file, --schema, JSON output, Docker, GitHub Action, pre-commit | 109 baseline | v1.0.0–v1.2.0 |
| 009 | feat/session-009-migrations-dir | `--from-migrations-dir` | — | — |
| 010 | feat/session-010-ai-explain | `--explain` (AIExplainer) | 36 | v1.3.0 |
| 011 | feat/session-011-ai-rollback | `--rollback` (AIRollback) | 42 | — |
| 012 | feat/session-012-ai-advise | `--advise` (AIAdvisor) + `classify_statement_risk()` | 33 | — |
| 013 | feat/session-013-ai-generate | `--generate` (AIGenerator) + safety rules | 33 | v1.4.0 |

**Test totals:** 175 passing, 2 skipped (226 collected including
Postgres-dependent tests). 144 of those are AI suite tests.

---

## 5. Feature Roadmap

### Free Tier — Remaining Sessions

The free tier rule: **if it runs locally on the user's machine with
their own credentials, it's free.**

| Session | Feature | Description |
|---|---|---|
| 014 | `--explain-drift` | Schema drift detection and explanation between two points in time. One-time local execution is free; managed/scheduled monitoring is enterprise. |
| 015 | `--document` | AI-generated schema documentation. One-time generation is free; continuously updated hosted documentation is enterprise. |
| 016 | pgvector diffing | First-class support for pgvector extension objects in schema diffs. |

### Enterprise Tier — Post-Free-Suite

The enterprise rule: **if it requires MigraDiff to host something,
manage something, or store something on the customer's behalf, it's
enterprise.**

| Feature | Description | Infrastructure Required |
|---|---|---|
| Shadow Run | Simulate migrations against ephemeral cloned databases; report locking behavior, rewrite risk, and estimated duration at actual data scale. | Firecracker microVMs, ephemeral Postgres instances, `pg_stat_activity` / `pg_locks` profiling |
| Hosted AI key | MigraDiff absorbs Anthropic API cost; customer doesn't need their own key. Usage-metered. | API key management, metering, billing |
| Team RBAC | Role-based access control and multi-stage approval workflows for migrations. | Account management, permissions storage |
| SAML / SSO | Enterprise identity provider integration (SAML 2.0, OIDC). | Identity layer (`python3-saml`, `authlib`) |
| Audit trail dashboard | Hosted dashboard showing migration history, approvals, risk assessments, and compliance evidence. | Data persistence, dashboard hosting |
| PR comment injection | Managed GitHub App that posts migration diffs and risk assessments as PR comments automatically. | GitHub App, webhooks |
| `--explain-drift` managed | Scheduled drift monitoring with alerts and dashboard. | Scheduled jobs, alert delivery |
| `--document` hosted | Continuously updated schema documentation portal. | Hosting, persistence |
| VS Code extension (premium) | Shared diff history, approval workflows in IDE, team account features. (Base extension is free and open source.) | Team account infrastructure |
| Compliance reporting | NIST / EU AI Act mapping of schema changes to control frameworks. | Report generation, export |

---

## 6. Enterprise Gating Architecture

Three layers:

### Layer 1 — License Key

Offline-verifiable, HMAC-signed license key. No license server call
required — works in air-gapped environments.

```
MIGRADIFF-ENT-{base64_encoded_payload}-{hmac_signature}
```

Payload:
```json
{
  "customer": "acme-corp",
  "tier": "enterprise",
  "features": ["shadow_run", "saml", "audit", "rbac"],
  "issued_at": "2026-05-30",
  "expires_at": "2027-05-30",
  "seats": 25
}
```

HMAC signed with Lateos private key. Verification uses public key
bundled with the tool.

### Layer 2 — Feature Flags

```python
from migra.license import require_feature

@require_feature("shadow_run")
def run_shadow_simulation(config):
    ...
```

Clean error on missing feature:
```
MigraDiff Enterprise: shadow_run requires an Enterprise license.
Contact enterprise@lateos.ai or visit https://migradiff.com/enterprise
```

### Layer 3 — Telemetry (Enterprise Only)

License validation calls home only for enterprise features (seat
counting, usage metering). Free tier has zero telemetry.

---

## 7. Business Model

### Pricing Tiers (Planned)

| Tier | Price | Target |
|---|---|---|
| Free (open source) | $0 | Individual developers, open-source projects |
| Core support | ~$5K/year | Teams needing SLA and priority bug fixes |
| Managed service | ~$20K/year | Teams needing Shadow Run, hosted drift monitoring, RBAC |
| Enterprise | Custom | Large orgs needing SAML/SSO, audit compliance, on-prem |

### Revenue Model

- Free tier builds community, adoption, and acquisition signal
- Core support converts power users who need SLA guarantees
- Managed service converts teams who need hosted infrastructure
- Enterprise converts regulated industries (healthcare, fintech, gov)

### Unit Economics Target

- 150 Core customers × $5K = $750K
- 50 Managed customers × $20K = $1M
- Premium + consulting = upside
- **Y1 ARR target: $1–2M**

---

## 8. Go-to-Market Strategy

### Phase 1 — Community Adoption (Current)

- PyPI distribution (`pip install migradiff`)
- Docker image for zero-install usage
- GitHub Action for CI integration
- Pre-commit hook for local development
- README positions MigraDiff as the drop-in `migra` continuation
- Social: Reddit r/PostgreSQL, Hacker News (Show HN), X, LinkedIn
- `enterprise@lateos.ai` in README for inbound enterprise interest

### Phase 2 — Design Partner (Next)

- Identify 1–3 enterprise design partners from inbound interest
- Build enterprise features against real requirements, not guesses
- Do not build enterprise infrastructure speculatively

### Phase 3 — Managed Service Launch

- Shadow Run as flagship enterprise feature
- Landing page with pricing tiers
- Stripe billing integration
- Free trial → paid conversion funnel

### Target Buyers

- Platform engineering teams managing PostgreSQL schema changes
- DBAs in regulated industries (healthcare, fintech)
- Supabase users (natural ecosystem fit)
- Teams migrating from deprecated `djrobstep/migra`

### Sales Advantage

Leo's healthcare field service engineering background gives direct
credibility in clinical/hospital environments where PostgreSQL powers
EHR integrations and compliance is mandatory.

---

## 9. Exit Strategy

### Target Acquirers

| Acquirer | Rationale | Estimated Multiple |
|---|---|---|
| Supabase | Postgres-native, "backend for everyone" platform, already owns database tooling | 10–12x ARR |
| Redgate | DevOps platform expansion, already acquires database diff/migration tools | 8–10x ARR |
| AWS | RDS tooling ecosystem, could bundle with Aurora/RDS | Strategic premium |

### Timeline

- **Year 1:** Ship free AI suite, build community, land first enterprise
  design partners, reach $1–2M ARR
- **Year 2:** Scale managed service, stack with pgAudit/WAL-G/pgBackRest
  forks for combined $3–4M ARR
- **Year 2–3:** Exit at $15–25M to Supabase or Redgate

### Portfolio Context

MigraDiff is the lead project in a stack of deprecated PostgreSQL tool
forks, all following the same playbook (fork → fix → modernize → add
enterprise features → acquisition target):

1. **MigraDiff** (migra fork) — schema diff — active, v1.4.0
2. **pgAudit wrapper** — compliance audit logging — planned
3. **WAL-G fork** — cloud-native backup workflows (Go) — planned
4. **pgBackRest fork** — backup/restore (C, v2.58.0 final) — planned

Combined portfolio targets $3–4M ARR and $15–25M exit.

---

## 10. Development Practices

- **Tests-first:** Confirm runtime failure before writing implementation
- **No vibe-coding:** Every prompt has explicit stop conditions
- **CLAUDE.md as convention anchor:** All coding agents read it first
- **Sequential execution:** OpenCode Zen with `--delay=5` for rate limiting
- **Tool separation:** Claude (Anthropic) for architecture, strategy,
  prompt engineering, and dataset quality review; implementation
  delegated to coding agents (Minimax M2.5, GLM-5.1/DeepSeek V4 Flash)
- **Linting:** flake8 (0 warnings) and black (clean) enforced on every
  session exit
- **Branching:** `feat/session-NNN-feature-name`, local commit only
  during session, push on release
- **Commit format:** Defined in CLAUDE.md

---

## 11. Risk Management

| Risk | Mitigation |
|---|---|
| Anthropic API changes | AI features are optional; core diff is dependency-free. Lazy import pattern isolates breakage. |
| Upstream revival | Unlikely (deprecated 2024, archived). Fork is already ahead on features. |
| Competitor (e.g. pgAdmin adds diff) | AI suite is differentiator; no PostgreSQL tool has schema-aware AI migration generation. |
| Low enterprise conversion | Free tier builds acquisition signal regardless; acquirer buys community + technology, not just revenue. |
| Shadow Run operational complexity | Don't build until design partner requests it. Firecracker microVM lifecycle is well-documented. |
| Key-person risk | MIT license, clean codebase, comprehensive tests — acquirable even without founder. |

---

## 12. Key Contacts

| Role | Contact |
|---|---|
| Maintainer | Leo — leo@lateos.ai |
| Enterprise inquiries | enterprise@lateos.ai |
| LinkedIn | linkedin.com/in/roongrunchai-chong-c-ab9742108 |
| GitHub | github.com/migradiff/migra |

---

## Document History

| Version | Date | Changes |
|---|---|---|
| 1.0 | June 1, 2026 | Initial formal plan — compiled from sessions 001–013, roadmap discussions, and business strategy. |
