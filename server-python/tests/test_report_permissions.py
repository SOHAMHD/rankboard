"""Who can do what to a report.

Report deletion is destructive and unrecoverable — `delete_version` removes the
row, and a sent report is a record of something a client received. Team members
author reports but must not be able to delete them.

These assertions are about the wiring, not the logic: the gate is a decorator on
the route, so the failure mode isn't a wrong answer, it's a missing dependency
nobody notices. Asserted against the route table so that adding a delete route,
or loosening this one, fails here.
"""

import inspect

import pytest

from app.permissions import (
    AUTHOR_ROLES,
    DELETER_ROLES,
    PERMISSIONS,
    SENDER_ROLES,
    can,
)
from app.routers import reports


# ── the role sets ─────────────────────────────────────────────────────

def test_team_cannot_delete_reports():
    assert "Team" not in DELETER_ROLES


def test_team_cannot_send_reports():
    # Sending is the other irreversible one: it puts a PDF in a client's inbox.
    assert "Team" not in SENDER_ROLES


def test_team_can_still_author_reports():
    # The point of the role — Team writes reports, Admin releases and removes them.
    assert "Team" in AUTHOR_ROLES


def test_clients_can_do_none_of_the_three():
    for role_set in (AUTHOR_ROLES, SENDER_ROLES, DELETER_ROLES):
        assert "Client" not in role_set


def test_only_admins_delete_or_send():
    assert set(DELETER_ROLES) == {"Super Admin", "Admin"}
    assert set(SENDER_ROLES) == {"Super Admin", "Admin"}


# ── the route wiring ──────────────────────────────────────────────────

def delete_routes():
    return [r for r in reports.router.routes if "DELETE" in getattr(r, "methods", set())]


def test_there_is_exactly_one_way_to_delete_a_report():
    """A second delete route added without a gate is the realistic regression."""
    assert len(delete_routes()) == 1


def test_the_delete_route_is_gated_on_the_deleter_roles():
    route = delete_routes()[0]
    src = inspect.getsource(route.endpoint)
    assert "require_roles(*DELETER_ROLES)" in src
    # Not AUTHOR_ROLES — the mistake would be copying it from a neighbouring
    # handler, every one of which uses AUTHOR_ROLES.
    assert "AUTHOR_ROLES" not in src


def test_the_delete_route_also_checks_project_access():
    # Being an Admin isn't enough; the report has to be on a project you can see.
    assert "_require_version_access" in inspect.getsource(delete_routes()[0].endpoint)


# ── the permission table the client reads ─────────────────────────────

@pytest.mark.parametrize("action", ["deleteProject", "deleteKeyword", "manageUsers"])
def test_team_holds_no_destructive_permission(action):
    # The client hides its delete controls from `user.permissions`, which is this
    # table. Report deletion isn't in it — it's role-based via isReportDeleter —
    # but the neighbouring destructive actions must stay shut for Team too.
    assert can("Team", action) is False


def test_every_role_is_present_in_the_table():
    # A role missing here gets an empty dict from can(), which fails closed —
    # correct, but silently, so assert the table is complete instead.
    assert set(PERMISSIONS) == {"Super Admin", "Admin", "Team", "Client"}
