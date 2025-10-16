"""Tests for CreditsAuthenticator / CreditsAuthenticator"""

import asyncio

import pytest

from jupyterhub_credit_service.orm import UserCredits as ORMUserCredits

from .conftest import MockCreditsAuthenticator

available_projects = [
    {"name": "community1", "cap": 1000, "grant_interval": 600, "grant_value": 60},
    {"name": "community2", "cap": 7, "grant_interval": 1200, "grant_value": 120},
]


@pytest.mark.asyncio
async def test_credits_enabled_flag():
    # Enabled by default
    auth = MockCreditsAuthenticator()
    assert auth.credits_enabled is True

    # Disabled explicitly
    auth_disabled = MockCreditsAuthenticator()
    auth_disabled.credits_enabled = False
    assert auth_disabled.credits_enabled is False


@pytest.mark.asyncio
async def test_credits_user_cap_integer(app, user):
    app.authenticator.credits_user_cap = 105
    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 105


@pytest.mark.asyncio
async def test_credits_user_cap_function_username(app, users):
    user1, user2 = users

    def user_cap(username, groups, is_admin):
        if username == user1.name:
            return 150
        return 100

    app.authenticator.credits_user_cap = user_cap
    await app.login_user(user1.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits.cap == 150

    await app.login_user(user2.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits.cap == 100


@pytest.mark.asyncio
async def test_credits_user_cap_function_admin(app, user, admin_user):
    def user_cap(username, groups, is_admin):
        if is_admin:
            return 150
        return 100

    app.authenticator.credits_user_cap = user_cap
    await app.login_user(admin_user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == admin_user.name)
        .first()
    )
    assert user_credits.cap == 150

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100


@pytest.mark.asyncio
async def test_credits_user_cap_function_group(app, users, group):
    user1, user2 = users
    group.users.append(user1.orm_user)
    app.db.commit()

    def user_cap(username, groups, is_admin):
        if group.name in [g.name for g in groups]:
            return 150
        return 100

    app.authenticator.credits_user_cap = user_cap
    await app.login_user(user1.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits.cap == 150

    await app.login_user(user2.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits.cap == 100


@pytest.mark.asyncio
async def test_credits_user_cap_function_username_coroutine(app, users):
    user1, user2 = users

    async def user_cap(username, groups, is_admin):
        if username == user1.name:
            return 150
        return 100

    app.authenticator.credits_user_cap = user_cap
    await app.login_user(user1.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits.cap == 150

    await app.login_user(user2.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits.cap == 100


@pytest.mark.asyncio
async def test_credits_user_grant_value_integer(app, user):
    app.authenticator.credits_user_grant_value = 15
    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.grant_value == 15


@pytest.mark.asyncio
async def test_credits_user_grant_value_function_username(app, users):
    user1, user2 = users

    def user_grant_value(username, groups, is_admin):
        if username == user1.name:
            return 20
        return 10

    app.authenticator.credits_user_grant_value = user_grant_value
    await app.login_user(user1.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits.grant_value == 20

    await app.login_user(user2.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits.grant_value == 10


@pytest.mark.asyncio
async def test_credits_user_grant_value_function_admin(app, user, admin_user):
    def user_grant_value(username, groups, is_admin):
        if is_admin:
            return 20
        return 10

    app.authenticator.credits_user_grant_value = user_grant_value
    await app.login_user(admin_user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == admin_user.name)
        .first()
    )
    assert user_credits.grant_value == 20

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.grant_value == 10


@pytest.mark.asyncio
async def test_credits_user_grant_value_function_group(app, users, group):
    user1, user2 = users
    group.users.append(user1.orm_user)
    app.db.commit()

    def user_grant_value(username, groups, is_admin):
        if group.name in [g.name for g in groups]:
            return 20
        return 10

    app.authenticator.credits_user_grant_value = user_grant_value
    await app.login_user(user1.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits.grant_value == 20

    await app.login_user(user2.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits.grant_value == 10


@pytest.mark.asyncio
async def test_credits_user_grant_value_function_username_coroutine(app, users):
    user1, user2 = users

    async def user_grant_value(username, groups, is_admin):
        if username == user1.name:
            return 20
        return 10

    app.authenticator.credits_user_grant_value = user_grant_value
    await app.login_user(user1.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits.grant_value == 20

    await app.login_user(user2.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits.grant_value == 10


@pytest.mark.asyncio
async def test_credits_available_projects_list_user_project(app, users):
    app.authenticator.credits_available_projects = available_projects

    user1, user2 = users

    def user_project(username, groups, is_admin):
        if username == user1.name:
            return "community1"
        elif username == user2.name:
            return "community2"
        return None

    app.authenticator.credits_user_project = user_project
    await app.login_user(user1.name)
    await app.login_user(user2.name)
    user_credits1 = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits1.project.name == "community1"

    user_credits2 = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits2.project.name == "community2"


@pytest.mark.asyncio
async def test_credits_available_projects_list_user_projects_noproj(app, users):
    app.authenticator.credits_available_projects = available_projects

    user1, user2 = users

    def user_projects(username, groups, is_admin):
        if username == user1.name:
            return "community1"
        return None

    app.authenticator.credits_user_project = user_projects
    await app.login_user(user1.name)
    await app.login_user(user2.name)
    user_credits1 = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits1.project.name == "community1"

    user_credits2 = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits2.project == None


@pytest.mark.asyncio
async def test_credits_user_grant_interval_integer(app, user):
    app.authenticator.credits_user_grant_interval = 900
    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.grant_interval == 900


@pytest.mark.asyncio
async def test_credits_user_grant_interval_function_username(app, users):
    user1, user2 = users

    def user_grant_interval(username, groups, is_admin):
        if username == user1.name:
            return 1200
        return 600

    app.authenticator.credits_user_grant_interval = user_grant_interval
    await app.login_user(user1.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits.grant_interval == 1200

    await app.login_user(user2.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits.grant_interval == 600


@pytest.mark.asyncio
async def test_credits_user_grant_interval_function_admin(app, user, admin_user):
    def user_grant_interval(username, groups, is_admin):
        if is_admin:
            return 1200
        return 600

    app.authenticator.credits_user_grant_interval = user_grant_interval
    await app.login_user(admin_user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == admin_user.name)
        .first()
    )
    assert user_credits.grant_interval == 1200

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.grant_interval == 600


@pytest.mark.asyncio
async def test_credits_user_grant_interval_function_group(app, users, group):
    user1, user2 = users
    group.users.append(user1.orm_user)
    app.db.commit()

    def user_grant_interval(username, groups, is_admin):
        if group.name in [g.name for g in groups]:
            return 1200
        return 600

    app.authenticator.credits_user_grant_interval = user_grant_interval
    await app.login_user(user1.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits.grant_interval == 1200

    await app.login_user(user2.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits.grant_interval == 600


@pytest.mark.asyncio
async def test_credits_user_grant_interval_function_username_coroutine(app, users):
    user1, user2 = users

    async def user_grant_interval(username, groups, is_admin):
        if username == user1.name:
            return 1200
        return 600

    app.authenticator.credits_user_grant_interval = user_grant_interval
    await app.login_user(user1.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user1.name)
        .first()
    )
    assert user_credits.grant_interval == 1200

    await app.login_user(user2.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user2.name)
        .first()
    )
    assert user_credits.grant_interval == 600


@pytest.mark.asyncio
async def test_credits_task_post_hook_async_called():
    hook_called = []

    async def post_hook():
        hook_called.append(True)

    _ = MockCreditsAuthenticator(
        credits_task_interval=1, credits_task_post_hook=post_hook
    )

    await asyncio.sleep(1)

    assert hook_called, "Post-task hook was not executed"


@pytest.mark.asyncio
async def test_credits_task_post_hook_called():
    hook_called = []

    def post_hook():
        hook_called.append(True)

    _ = MockCreditsAuthenticator(
        credits_task_interval=1, credits_task_post_hook=post_hook
    )

    await asyncio.sleep(1)

    assert hook_called, "Post-task hook was not executed"
