# CI/CD Notes

## Known Limitations

### schemainspect + setuptools dependency

The `schemainspect` package (a dependency for PostgreSQL introspection) 
uses deprecated `pkg_resources` from `setuptools`. This creates an import-time 
dependency that requires `setuptools` to be available at Python runtime.

**Impact:** GitHub Actions CI requires explicit setuptools installation steps.

**Mitigation:** Added `setuptools` to pyproject.toml dependencies and 
CI workflow installs it before running tests.

**Background:** schemainspect is unmaintained by upstream (djrobstep). 
A future migration to a maintained schema inspection library would resolve this.

---

## Workflow

- **CI** runs on: push to `master`, PRs to `master`
  - Lint (flake8, black)
  - Test matrix (4 Python versions × 4 Postgres versions = 16 jobs)
  - Coverage report

- **CD** runs on: git tags matching `v*`
  - Build package
  - Publish to PyPI
  - Create GitHub release
