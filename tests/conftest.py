import sqlalchemy as sa
import sqlbag.createdrop as sc


def _patched_database_exists(s, name):
    c = sc.connection_from_s_or_c(s)
    dbtype = c.engine.dialect.name
    if dbtype == "postgresql":
        q = "SELECT 1 FROM pg_catalog.pg_database WHERE datname = :name"
    elif dbtype == "mysql":
        q = "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = :name"
    else:
        return sc._database_exists(s, name)
    return bool(c.execute(sa.text(q), {"name": name}).scalar())


sc._database_exists = _patched_database_exists
