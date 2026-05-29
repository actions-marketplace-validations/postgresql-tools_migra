# Changelog

## [Unreleased]

### Fixed
- Updated test fixtures to match current schemainspect view column
  alias output — resolves 6 pre-existing test failures
  (enumdeps, triggers3, dependencies, dependencies2, dependencies3, dependencies4)

### Added
- `--from-file` mode: diff `pg_dump -s` schema files directly without
  a live database connection — no production credentials required
- `.pre-commit-hooks.yaml`: pre-commit hook for local schema drift
  detection; example configuration in `pre-commit-config.example.yaml`
- `--output json` mode: structured diff output with per-statement risk
  classification (safe / warning / destructive) and summary metadata;
  credentials redacted from connection string fields
- Dockerfile: python:3.12-slim base, non-root user, minimal image size
- .dockerignore: excludes tests, docs, and dev assets from image
- docker-build.sh: convenience script for local image builds
- requirements.txt: pinned runtime dependencies for reproducible builds
