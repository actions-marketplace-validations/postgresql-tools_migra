from __future__ import unicode_literals

import json
from types import SimpleNamespace

from migra.changes import _format_comment_on, _get_comment_changes
from migra.command import format_json_output, classify_sql_statement


class _Row:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _MockInspector:
    def __init__(
        self,
        relations=None,
        functions=None,
        types=None,
        schemas=None,
        constraints=None,
        only_schema=None,
        exclude_schema=None,
    ):
        self.c = SimpleNamespace()
        self.only_schema = only_schema
        self.exclude_schema = exclude_schema
        self._data = {}
        self._data["relations"] = relations or []
        self._data["functions"] = functions or []
        self._data["types"] = types or []
        self._data["schemas"] = schemas or []
        self._data["constraints"] = constraints or []

    def execute(self, sql, *args, **kwargs):
        sql_str = str(sql)
        if "pg_constraint" in sql_str and "conname" in sql_str:
            return self._data["constraints"]
        if "pg_proc" in sql_str and "proname" in sql_str:
            return self._data["functions"]
        if "pg_type" in sql_str and "typname" in sql_str:
            return self._data["types"]
        if (
            "pg_namespace" in sql_str
            and "conname" not in sql_str
            and "relname" not in sql_str
        ):
            return self._data["schemas"]
        if "relname" in sql_str:
            return self._data["relations"]
        return []


class TestFormatCommentOn:
    def test_table(self):
        result = _format_comment_on(("TABLE", "public", "users"), "User accounts")
        assert result == 'COMMENT ON TABLE "public"."users" IS \'User accounts\';'

    def test_table_null(self):
        result = _format_comment_on(("TABLE", "public", "users"), None)
        assert result == 'COMMENT ON TABLE "public"."users" IS NULL;'

    def test_table_empty_string(self):
        result = _format_comment_on(("TABLE", "public", "users"), "")
        assert result == 'COMMENT ON TABLE "public"."users" IS \'\';'

    def test_column(self):
        result = _format_comment_on(
            ("COLUMN", "public", "users", "email"), "Primary email"
        )
        assert result == (
            'COMMENT ON COLUMN "public"."users"."email" IS \'Primary email\';'
        )

    def test_column_null(self):
        result = _format_comment_on(("COLUMN", "public", "users", "email"), None)
        assert result == 'COMMENT ON COLUMN "public"."users"."email" IS NULL;'

    def test_view(self):
        result = _format_comment_on(("VIEW", "public", "user_view"), "User view")
        assert result == ('COMMENT ON VIEW "public"."user_view" IS \'User view\';')

    def test_materialized_view(self):
        result = _format_comment_on(
            ("MATERIALIZED VIEW", "public", "user_mv"), "Materialized"
        )
        expected = (
            'COMMENT ON MATERIALIZED VIEW "public"."user_mv" IS \'Materialized\';'
        )
        assert result == expected

    def test_function(self):
        result = _format_comment_on(
            ("FUNCTION", "public", "notify_user", "integer, text"), "Send notification"
        )
        expected = (
            'COMMENT ON FUNCTION "public"."notify_user"(integer, text)'
            " IS 'Send notification';"
        )
        assert result == expected

    def test_sequence(self):
        result = _format_comment_on(
            ("SEQUENCE", "public", "user_id_seq"), "User ID sequence"
        )
        assert result == (
            'COMMENT ON SEQUENCE "public"."user_id_seq" IS \'User ID sequence\';'
        )

    def test_type(self):
        result = _format_comment_on(
            ("TYPE", "public", "user_status"), "User status enum"
        )
        assert result == (
            'COMMENT ON TYPE "public"."user_status" IS \'User status enum\';'
        )

    def test_index(self):
        result = _format_comment_on(
            ("INDEX", "public", "users_email_idx"), "Email index"
        )
        assert result == (
            'COMMENT ON INDEX "public"."users_email_idx" IS \'Email index\';'
        )

    def test_constraint(self):
        result = _format_comment_on(
            ("CONSTRAINT", "public", "users_pkey", "users"), "Primary key"
        )
        expected = (
            'COMMENT ON CONSTRAINT "users_pkey" ON "public"."users"'
            " IS 'Primary key';"
        )
        assert result == expected

    def test_schema(self):
        result = _format_comment_on(("SCHEMA", "public"), "Public schema")
        assert result == "COMMENT ON SCHEMA \"public\" IS 'Public schema';"

    def test_single_quotes(self):
        text = "User's primary email"
        result = _format_comment_on(("TABLE", "public", "users"), text)
        assert result == (
            "COMMENT ON TABLE \"public\".\"users\" IS 'User''s primary email';"
        )

    def test_newlines(self):
        text = "Line one\nLine two"
        result = _format_comment_on(("TABLE", "public", "users"), text)
        assert "Line one\nLine two" in result

    def test_unicode(self):
        text = "Usu\u00e1rio"
        result = _format_comment_on(("TABLE", "public", "users"), text)
        assert result == ('COMMENT ON TABLE "public"."users" IS \'Usu\u00e1rio\';')


class TestCommentDiffNoComments:
    def test_no_comments_both_sides(self):
        i_from = _MockInspector()
        i_target = _MockInspector()
        result = _get_comment_changes(i_from, i_target)
        assert list(result) == []

    def test_comment_on_same_both_sides(self):
        row = _Row(
            relname="users",
            schema_name="public",
            description="Accounts",
            objsubid=0,
            column_name=None,
            relkind="r",
        )
        i_from = _MockInspector(relations=[row])
        i_target = _MockInspector(relations=[row])
        result = _get_comment_changes(i_from, i_target)
        assert list(result) == []


class TestCommentDiffAdded:
    def test_added_to_table(self):
        row = _Row(
            relname="users",
            schema_name="public",
            description="Accounts",
            objsubid=0,
            column_name=None,
            relkind="r",
        )
        i_from = _MockInspector()
        i_target = _MockInspector(relations=[row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == ('COMMENT ON TABLE "public"."users" IS \'Accounts\';')

    def test_added_to_column(self):
        row = _Row(
            relname="users",
            schema_name="public",
            description="Email",
            objsubid=1,
            column_name="email",
            relkind="r",
        )
        i_from = _MockInspector()
        i_target = _MockInspector(relations=[row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == ('COMMENT ON COLUMN "public"."users"."email" IS \'Email\';')

    def test_added_to_view(self):
        row = _Row(
            relname="user_v",
            schema_name="public",
            description="View",
            objsubid=0,
            column_name=None,
            relkind="v",
        )
        i_from = _MockInspector()
        i_target = _MockInspector(relations=[row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == ('COMMENT ON VIEW "public"."user_v" IS \'View\';')

    def test_added_to_materialized_view(self):
        row = _Row(
            relname="user_mv",
            schema_name="public",
            description="MV",
            objsubid=0,
            column_name=None,
            relkind="m",
        )
        i_from = _MockInspector()
        i_target = _MockInspector(relations=[row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        expected = 'COMMENT ON MATERIALIZED VIEW "public"."user_mv" IS \'MV\';'
        assert result[0] == expected

    def test_added_to_function(self):
        row = _Row(
            proname="notify",
            schema_name="public",
            description="Notify",
            identity_args="integer, text",
        )
        i_from = _MockInspector()
        i_target = _MockInspector(functions=[row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        expected = (
            'COMMENT ON FUNCTION "public"."notify"(integer, text)' " IS 'Notify';"
        )
        assert result[0] == expected

    def test_added_to_sequence(self):
        row = _Row(
            relname="user_seq",
            schema_name="public",
            description="Seq",
            objsubid=0,
            column_name=None,
            relkind="S",
        )
        i_from = _MockInspector()
        i_target = _MockInspector(relations=[row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == ('COMMENT ON SEQUENCE "public"."user_seq" IS \'Seq\';')

    def test_added_to_type(self):
        row = _Row(
            typname="user_status", schema_name="public", description="Status enum"
        )
        i_from = _MockInspector()
        i_target = _MockInspector(types=[row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == (
            'COMMENT ON TYPE "public"."user_status" IS \'Status enum\';'
        )

    def test_added_to_index(self):
        row = _Row(
            relname="users_email_idx",
            schema_name="public",
            description="Index",
            objsubid=0,
            column_name=None,
            relkind="i",
        )
        i_from = _MockInspector()
        i_target = _MockInspector(relations=[row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == (
            'COMMENT ON INDEX "public"."users_email_idx" IS \'Index\';'
        )

    def test_added_to_constraint(self):
        row = _Row(
            conname="users_pkey",
            schema_name="public",
            table_name="users",
            description="PK",
        )
        i_from = _MockInspector()
        i_target = _MockInspector(constraints=[row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        expected = 'COMMENT ON CONSTRAINT "users_pkey" ON "public"."users"' " IS 'PK';"
        assert result[0] == expected

    def test_added_to_schema(self):
        row = _Row(schema_name="public", description="Public schema")
        i_from = _MockInspector()
        i_target = _MockInspector(schemas=[row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == ("COMMENT ON SCHEMA \"public\" IS 'Public schema';")


class TestCommentDiffRemoved:
    def test_removed_from_table(self):
        row = _Row(
            relname="users",
            schema_name="public",
            description="Old",
            objsubid=0,
            column_name=None,
            relkind="r",
        )
        i_from = _MockInspector(relations=[row])
        i_target = _MockInspector()
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == ('COMMENT ON TABLE "public"."users" IS NULL;')

    def test_removed_from_column(self):
        row = _Row(
            relname="users",
            schema_name="public",
            description="Old",
            objsubid=1,
            column_name="email",
            relkind="r",
        )
        i_from = _MockInspector(relations=[row])
        i_target = _MockInspector()
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == ('COMMENT ON COLUMN "public"."users"."email" IS NULL;')


class TestCommentDiffModified:
    def test_changed_on_table(self):
        from_row = _Row(
            relname="users",
            schema_name="public",
            description="Old",
            objsubid=0,
            column_name=None,
            relkind="r",
        )
        to_row = _Row(
            relname="users",
            schema_name="public",
            description="New",
            objsubid=0,
            column_name=None,
            relkind="r",
        )
        i_from = _MockInspector(relations=[from_row])
        i_target = _MockInspector(relations=[to_row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == ('COMMENT ON TABLE "public"."users" IS \'New\';')

    def test_changed_on_column(self):
        from_row = _Row(
            relname="users",
            schema_name="public",
            description="Old",
            objsubid=1,
            column_name="email",
            relkind="r",
        )
        to_row = _Row(
            relname="users",
            schema_name="public",
            description="New",
            objsubid=1,
            column_name="email",
            relkind="r",
        )
        i_from = _MockInspector(relations=[from_row])
        i_target = _MockInspector(relations=[to_row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == ('COMMENT ON COLUMN "public"."users"."email" IS \'New\';')


class TestCommentDiffEdgeCases:
    def test_multiple_comments_diff(self):
        table_row = _Row(
            relname="t1",
            schema_name="public",
            description="T1",
            objsubid=0,
            column_name=None,
            relkind="r",
        )
        col_row = _Row(
            relname="t1",
            schema_name="public",
            description="Col",
            objsubid=1,
            column_name="c1",
            relkind="r",
        )
        i_from = _MockInspector()
        i_target = _MockInspector(relations=[table_row, col_row])
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 2
        assert result[0] == ('COMMENT ON COLUMN "public"."t1"."c1" IS \'Col\';')
        assert result[1] == ('COMMENT ON TABLE "public"."t1" IS \'T1\';')

    def test_empty_string_vs_null(self):
        empty_row = _Row(
            relname="t1",
            schema_name="public",
            description="",
            objsubid=0,
            column_name=None,
            relkind="r",
        )
        i_from = _MockInspector(relations=[empty_row])
        i_target = _MockInspector()
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == ('COMMENT ON TABLE "public"."t1" IS NULL;')

    def test_nonexistent_column_comment_ignored(self):
        col_row = _Row(
            relname="users",
            schema_name="public",
            description="Stale",
            objsubid=99,
            column_name="nonexistent",
            relkind="r",
        )
        i_from = _MockInspector(relations=[col_row])
        i_target = _MockInspector()
        result = _get_comment_changes(i_from, i_target)
        assert len(result) == 1
        assert result[0] == (
            'COMMENT ON COLUMN "public"."users"."nonexistent" IS NULL;'
        )


class TestCommentOnClassName:
    def test_table_quoted_identifiers(self):
        result = _format_comment_on(("TABLE", "my-schema", "my-table"), "Comment")
        assert result == ('COMMENT ON TABLE "my-schema"."my-table" IS \'Comment\';')

    def test_column_quoted_identifiers(self):
        result = _format_comment_on(
            ("COLUMN", "my-schema", "my-table", "my-col"), "Comment"
        )
        assert result == (
            'COMMENT ON COLUMN "my-schema"."my-table"."my-col" IS \'Comment\';'
        )

    def test_schema_quoted(self):
        result = _format_comment_on(("SCHEMA", "my-schema"), "Comment")
        assert result == ("COMMENT ON SCHEMA \"my-schema\" IS 'Comment';")

    def test_constraint_quoted(self):
        result = _format_comment_on(
            ("CONSTRAINT", "public", "my-con", "my-table"), "Comment"
        )
        assert result == (
            'COMMENT ON CONSTRAINT "my-con" ON "public"."my-table"' " IS 'Comment';"
        )


class TestCommentOnJsonOutput:
    def test_comment_on_json_safe_risk(self):
        stmts = [
            "COMMENT ON TABLE public.users IS 'User accounts';",
        ]
        json_out = format_json_output(stmts, "source", "target")
        data = json.loads(json_out)
        assert data["summary"]["risk_level"] == "low"
        assert data["summary"]["total_statements"] == 1
        assert data["statements"][0]["risk"] == "safe"

    def test_comment_on_json_summary(self):
        stmts = [
            "COMMENT ON TABLE public.users IS 'User accounts';",
            "CREATE TABLE public.t1 (id integer);",
        ]
        json_out = format_json_output(stmts, "source", "target")
        data = json.loads(json_out)
        assert data["summary"]["total_statements"] == 2
        assert data["summary"]["risk_level"] == "low"


class TestAppendTableComments:
    def test_table_comment_included(self):
        from migra.ai_explain import _append_table_comments
        from unittest.mock import MagicMock

        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row.objsubid = 0
        mock_row.attname = None
        mock_row.description = "Core user accounts table"
        mock_conn.execute.return_value = [mock_row]

        ctx = []
        _append_table_comments(mock_conn, "public", "users", ctx, [])
        assert any(
            'Comment on public.users: "Core user accounts table"' in p for p in ctx
        )

    def test_column_comment_included(self):
        from migra.ai_explain import _append_table_comments
        from unittest.mock import MagicMock

        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row.objsubid = 1
        mock_row.attname = "email"
        mock_row.description = "Primary email"
        mock_conn.execute.return_value = [mock_row]

        ctx = []
        _append_table_comments(mock_conn, "public", "users", ctx, [])
        assert any('Comment on public.users.email: "Primary email"' in p for p in ctx)

    def test_no_comments_no_crash(self):
        from migra.ai_explain import _append_table_comments
        from unittest.mock import MagicMock

        mock_conn = MagicMock()
        mock_conn.execute.return_value = []

        ctx = ["-- Table public.users:\nCREATE TABLE public.users ();"]
        _append_table_comments(mock_conn, "public", "users", ctx, [])
        # Should not crash, ctx unchanged
        assert len(ctx) == 1


class TestClassifyCommentOn:
    def test_classify_safe(self):
        info = classify_sql_statement(
            "COMMENT ON TABLE public.users IS 'User accounts';"
        )
        assert info["risk"] == "safe"

    def test_classify_column(self):
        info = classify_sql_statement(
            "COMMENT ON COLUMN public.users.email IS 'Email';"
        )
        assert info["risk"] == "safe"

    def test_classify_function(self):
        info = classify_sql_statement("COMMENT ON FUNCTION public.func() IS 'Func';")
        assert info["risk"] == "safe"

    def test_classify_is_null(self):
        info = classify_sql_statement("COMMENT ON TABLE public.users IS NULL;")
        assert info["risk"] == "safe"
