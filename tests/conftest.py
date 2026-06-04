import os

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


def _patched_create_database(db_url, template=None, wipe_if_existing=False):
    target_url = sc.make_url(db_url)
    dbtype = target_url.get_dialect().name
    if wipe_if_existing:
        sc.drop_database(db_url)
    if sc.database_exists(target_url):
        return False
    if dbtype == "sqlite":
        sc.can_select(target_url)
        return True
    with sc.admin_db_connection(target_url) as c:
        t = "template {}".format(sc.quoted_identifier(template)) if template else ""
        c.execute(
            sa.text(
                "create database {} {}".format(
                    sc.quoted_identifier(target_url.database), t
                )
            )
        )
    return True


def _patched_drop_database(db_url):
    url = sc.make_url(db_url)
    dbtype = url.get_dialect().name
    name = url.database
    if not sc.database_exists(url):
        return False
    if dbtype == "sqlite":
        if name and name != ":memory:":
            os.remove(name)
        return True
    with sc.admin_db_connection(url) as c:
        if dbtype == "postgresql":
            c.execute(
                sa.text(
                    "revoke connect on database {} from public".format(
                        sc.quoted_identifier(name)
                    )
                )
            )
        sc.kill_other_connections(c, name, hardkill=True)
        c.execute(
            sa.text(
                "drop database if exists {}".format(sc.quoted_identifier(name))
            )
        )
    return True


sc._database_exists = _patched_database_exists
sc.create_database = _patched_create_database
sc.drop_database = _patched_drop_database
