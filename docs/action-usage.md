# MigraDiff GitHub Action — Usage

## Basic Usage (Connection Strings)

```yaml
- uses: postgresql-tools/migra@v1
  with:
    base_url: ${{ secrets.DB_PRODUCTION_URL }}
    head_url: ${{ secrets.DB_BRANCH_URL }}
```

## Schema Dump Files (No Live Connection Required)

```yaml
- uses: postgresql-tools/migra@v1
  with:
    base_file: schema_production.sql
    head_file: schema_branch.sql
```

## Fail on Destructive Operations

```yaml
- uses: postgresql-tools/migra@v1
  with:
    base_url: ${{ secrets.DB_PRODUCTION_URL }}
    head_url: ${{ secrets.DB_BRANCH_URL }}
    fail_on_destructive: "true"
```

## Migrations Directory

```yaml
- uses: postgresql-tools/migra@v1
  with:
    base_url: ${{ secrets.DB_PRODUCTION_URL }}
    migrations_dir: ./supabase/migrations
```

## JSON Output

```yaml
- uses: postgresql-tools/migra@v1
  id: schema_diff
  with:
    base_url: ${{ secrets.DB_PRODUCTION_URL }}
    head_url: ${{ secrets.DB_BRANCH_URL }}
    output_format: json

- name: Check for schema changes
  if: steps.schema_diff.outputs.has_changes == 'true'
  run: echo "Schema drift detected"
```
