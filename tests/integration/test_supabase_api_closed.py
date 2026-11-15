"""The Supabase public API must reach nothing: every public table has RLS and no grants (SPEC 10).

A new table without RLS, or one that anon or authenticated may read, breaks this test.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration

API_ROLES = ["anon", "authenticated"]
PUBLIC_TABLES = text(
    """
    SELECT c.relname, c.relrowsecurity
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r'
    ORDER BY c.relname
    """
)


def public_tables(session: Session) -> list[tuple[str, bool]]:
    return [(row[0], row[1]) for row in session.execute(PUBLIC_TABLES)]


def test_there_are_tables_to_check(session: Session) -> None:
    assert len(public_tables(session)) >= 14  # guards against a query that finds nothing


def test_every_public_table_has_row_level_security(session: Session) -> None:
    without_rls = [name for name, enabled in public_tables(session) if not enabled]
    assert without_rls == []


@pytest.mark.parametrize("role", API_ROLES)
def test_api_roles_cannot_select_from_any_public_table(session: Session, role: str) -> None:
    for name, _ in public_tables(session):
        # The savepoint lets the session go on after the expected permission error.
        with pytest.raises(DBAPIError, match="permission denied"), session.begin_nested():
            session.execute(text(f"SET LOCAL ROLE {role}"))
            session.execute(text(f'SELECT 1 FROM public."{name}" LIMIT 1'))


@pytest.mark.parametrize("role", API_ROLES)
def test_api_roles_have_no_privileges_on_public_tables(session: Session, role: str) -> None:
    granted = session.execute(
        text(
            """
            SELECT table_name, privilege_type FROM information_schema.role_table_grants
            WHERE table_schema = 'public' AND grantee = :role
            """
        ),
        {"role": role},
    ).all()
    assert granted == []


def test_a_new_table_starts_without_grants_for_the_api_roles(session: Session) -> None:
    session.execute(text("CREATE TABLE public.zz_closed_probe (id int)"))
    granted = session.execute(
        text(
            """
            SELECT grantee FROM information_schema.role_table_grants
            WHERE table_name = 'zz_closed_probe' AND grantee IN ('anon', 'authenticated')
            """
        )
    ).all()
    assert granted == []
