from __future__ import print_function, unicode_literals

import argparse
import os
import sys
from contextlib import contextmanager

from .migra import Migration
from .statements import UnsafeMigrationException


@contextmanager
def arg_context(x):
    if x == "EMPTY":
        yield None

    else:
        from sqlbag import S

        with S(x) as s:
            yield s


@contextmanager
def file_context(x, y):
    from sqlbag import S, load_sql_from_file, temporary_database

    with temporary_database(host="localhost") as d0, temporary_database(
        host="localhost"
    ) as d1:
        with S(d0) as s0:
            load_sql_from_file(s0, x)
        with S(d1) as s1:
            load_sql_from_file(s1, y)
        yield d0, d1


def parse_args(args):
    parser = argparse.ArgumentParser(description="Generate a database migration.")
    parser.add_argument(
        "--unsafe",
        dest="unsafe",
        action="store_true",
        help="Prevent migra from erroring upon generation of drop statements.",
    )
    parser.add_argument(
        "--schema",
        dest="schema",
        default=None,
        help="Restrict output to statements for a particular schema",
    )
    parser.add_argument(
        "--exclude_schema",
        dest="exclude_schema",
        default=None,
        help="Restrict output to statements for all schemas except the specified schema",
    )
    parser.add_argument(
        "--create-extensions-only",
        dest="create_extensions_only",
        action="store_true",
        default=False,
        help='Only output "create extension..." statements, nothing else.',
    )
    parser.add_argument(
        "--ignore-extension-versions",
        dest="ignore_extension_versions",
        action="store_true",
        default=False,
        help="Ignore the versions when comparing extensions.",
    )
    parser.add_argument(
        "--with-privileges",
        dest="with_privileges",
        action="store_true",
        default=False,
        help="Also output privilege differences (ie. grant/revoke statements)",
    )
    parser.add_argument(
        "--force-utf8",
        dest="force_utf8",
        action="store_true",
        default=False,
        help="Force UTF-8 encoding for output",
    )
    parser.add_argument(
        "--from-file",
        dest="from_file",
        action="store_true",
        default=False,
        help="Treat dburl_from and dburl_target as pg_dump -s file paths",
    )
    parser.add_argument("dburl_from", help="The database you want to migrate.")
    parser.add_argument(
        "dburl_target", help="The database you want to use as the target."
    )
    return parser.parse_args(args)


def run(args, out=None, err=None):
    if not out:
        out = sys.stdout  # pragma: no cover
    if not err:
        err = sys.stderr  # pragma: no cover

    if args.from_file:
        for path in [args.dburl_from, args.dburl_target]:
            if "://" in path:
                print(
                    "ERROR: --from-file expects file paths, but got a URL. "
                    "Drop --from-file to diff live databases.",
                    file=err,
                )
                return 1
            if not os.path.exists(path):
                print(
                    f"ERROR: file not found: {path}",
                    file=err,
                )
                return 1
        try:
            with file_context(args.dburl_from, args.dburl_target) as (
                d0_url,
                d1_url,
            ):
                args.dburl_from = d0_url
                args.dburl_target = d1_url
                return _run_inner(args, out, err)
        except Exception as e:
            print(
                f"ERROR: could not load SQL from files: {e}",
                file=err,
            )
            return 1

    return _run_inner(args, out, err)


def _run_inner(args, out=None, err=None):
    schema = args.schema
    exclude_schema = args.exclude_schema
    with arg_context(args.dburl_from) as ac0, arg_context(args.dburl_target) as ac1:
        m = Migration(
            ac0,
            ac1,
            schema=schema,
            exclude_schema=exclude_schema,
            ignore_extension_versions=args.ignore_extension_versions,
        )
        if args.unsafe:
            m.set_safety(False)
        if args.create_extensions_only:
            m.add_extension_changes(drops=False)
        else:
            m.add_all_changes(privileges=args.with_privileges)
        try:
            if m.statements:
                if args.force_utf8:
                    print(m.sql.encode("utf8"), file=out)
                else:
                    print(m.sql, file=out)
        except UnsafeMigrationException:
            print(
                "-- ERROR: destructive statements generated. Use the --unsafe flag to suppress this error.",
                file=err,
            )
            return 3

        if not m.statements:
            return 0

        else:
            return 2


def do_command():  # pragma: no cover
    args = parse_args(sys.argv[1:])
    status = run(args)
    sys.exit(status)
