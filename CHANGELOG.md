# Changelog

## [Unreleased]

### Fixed
- Updated test fixtures to match current schemainspect view column
  alias output — resolves 6 pre-existing test failures
  (enumdeps, triggers3, dependencies, dependencies2, dependencies3, dependencies4)

### Added
- `--from-file` mode: diff `pg_dump -s` schema files directly without
  a live database connection — no production credentials required
