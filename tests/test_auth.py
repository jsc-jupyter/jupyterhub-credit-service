"""Tests for CreditsAuthenticator / CreditsAuthenticator"""

import asyncio
import copy

import pytest

from jupyterhub_credit_service.orm import CreditsUser

user_credits_simple = {
    "name": "default",
    "cap": 500,
    "grant_value": 50,
    "grant_interval": 300,
}


def user_credits_simple_function(_, username, groups, is_admin, auth_state):
    return user_credits_simple


def user_credits_simple_function_list(_, username, groups, is_admin, auth_state):
    return [user_credits_simple]


async def async_user_credits_simple_function(_, username, groups, is_admin, auth_state):
    return user_credits_simple


async def async_user_credits_simple_function_list(
    _, username, groups, is_admin, auth_state
):
    return [user_credits_simple]


user_credits_simple_project = {
    "name": "community1",
    "cap": 500,
    "grant_value": 50,
    "grant_interval": 300,
    "project": {
        "name": "community1",
        "cap": 1000,
        "grant_interval": 600,
        "grant_value": 60,
    },
}

user_credits_simple_project_list = [
    {
        "name": "community1",
        "cap": 500,
        "grant_value": 50,
        "grant_interval": 300,
        "project": {
            "name": "community1",
            "cap": 1000,
            "grant_interval": 600,
            "grant_value": 60,
        },
    }
]

user_credits_multiple_w_default = [
    {
        "name": "systemA",
        "cap": 500,
        "grant_value": 50,
        "grant_interval": 300,
        "project": {
            "name": "systemA",
            "cap": 7,
            "grant_interval": 1200,
            "grant_value": 120,
        },
        "user_options": {"system": "A"},
    },
    {"name": "default", "cap": 600, "grant_value": 60, "grant_interval": 400},
]

user_credits_multiple_wo_default = [
    {
        "cap": 500,
        "name": "systemA",
        "grant_value": 50,
        "grant_interval": 300,
        "project": {
            "name": "systemA",
            "cap": 7,
            "grant_interval": 1200,
            "grant_value": 120,
        },
        "user_options": {"system": "A"},
    },
    {
        "name": "systemB",
        "cap": 600,
        "grant_value": 60,
        "grant_interval": 400,
        "project": {
            "name": "systemB",
            "cap": 7,
            "grant_interval": 1200,
            "grant_value": 120,
        },
        "user_options": {"system": "B"},
    },
]

user_credits_multiple_wo_default_multimatch = [
    {
        "name": "systemA",
        "cap": 500,
        "grant_value": 50,
        "grant_interval": 300,
        "project": {
            "name": "systemA",
            "cap": 7,
            "grant_interval": 1200,
            "grant_value": 120,
        },
        "user_options": {"system": "A"},
    },
    {
        "name": "systemA2",
        "cap": 600,
        "grant_value": 60,
        "grant_interval": 400,
        "project": {
            "name": "systemA2",
            "cap": 7,
            "grant_interval": 1200,
            "grant_value": 120,
        },
        "user_options": {"system": "A"},
    },
]


@pytest.mark.asyncio
async def test_credits_user_simple(app, user):
    app.authenticator.credits_user = user_credits_simple
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits_values = user_credits.credits_user_values
    assert user_credits_values is not None
    assert len(user_credits_values) == 1
    for key, value in user_credits_simple.items():
        assert getattr(user_credits_values[0], key) == value
    assert getattr(user_credits_values[0], "balance") == user_credits_simple["cap"]
    assert getattr(user_credits_values[0], "user_name") == user.name
    assert getattr(user_credits_values[0], "project_name") is None


@pytest.mark.asyncio
async def test_credits_user_simple_list(app, user):
    app.authenticator.credits_user = [user_credits_simple]
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits_values = user_credits.credits_user_values
    assert user_credits_values is not None
    assert len(user_credits_values) == 1
    for key, value in user_credits_simple.items():
        assert getattr(user_credits_values[0], key) == value
    assert getattr(user_credits_values[0], "balance") == user_credits_simple["cap"]
    assert getattr(user_credits_values[0], "user_name") == user.name
    assert getattr(user_credits_values[0], "project_name") is None


@pytest.mark.asyncio
async def test_credits_user_list_w_default(app, user):
    app.authenticator.credits_user = user_credits_multiple_w_default
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits_values = user_credits.credits_user_values
    assert user_credits_values is not None
    assert len(user_credits_values) == 2
    for key, value in user_credits_multiple_w_default[0].items():
        if key == "project":
            assert (
                getattr(user_credits_values[0], "project_name") == value["name"]
            ), "Key project/project_name does not match"
        else:
            assert (
                getattr(user_credits_values[0], key) == value
            ), f"Key {key} does not match"
    assert (
        getattr(user_credits_values[0], "balance")
        == user_credits_multiple_w_default[0]["cap"]
    )
    assert getattr(user_credits_values[0], "user_name") == user.name
    assert (
        getattr(user_credits_values[0], "user_options")
        == user_credits_multiple_w_default[0]["user_options"]
    )

    for key, value in user_credits_multiple_w_default[1].items():
        if key == "project":
            assert (
                getattr(user_credits_values[1], "project_name") == value["name"]
            ), "Key project/project_name does not match"
        else:
            assert (
                getattr(user_credits_values[1], key) == value
            ), f"Key {key} does not match"
    assert (
        getattr(user_credits_values[1], "balance")
        == user_credits_multiple_w_default[1]["cap"]
    )
    assert getattr(user_credits_values[1], "user_name") == user.name
    assert getattr(user_credits_values[1], "project_name") is None
    assert getattr(user_credits_values[1], "project") is None
    assert getattr(user_credits_values[1], "user_options") is None


@pytest.mark.asyncio
async def test_credits_user_list_wo_default(app, user):
    app.authenticator.credits_user = user_credits_multiple_wo_default
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits_values = user_credits.credits_user_values
    assert user_credits_values is not None
    assert len(user_credits_values) == 2
    for key, value in user_credits_multiple_wo_default[0].items():
        if key == "project":
            assert (
                getattr(user_credits_values[0], "project_name") == value["name"]
            ), "Key project/project_name does not match"
        else:
            assert (
                getattr(user_credits_values[0], key) == value
            ), f"Key {key} does not match"
    assert (
        getattr(user_credits_values[0], "balance")
        == user_credits_multiple_wo_default[0]["cap"]
    )
    assert getattr(user_credits_values[0], "user_name") == user.name
    assert (
        getattr(user_credits_values[0], "user_options")
        == user_credits_multiple_wo_default[0]["user_options"]
    )

    for key, value in user_credits_multiple_wo_default[1].items():
        if key == "project":
            assert (
                getattr(user_credits_values[1], "project_name") == value["name"]
            ), "Key project/project_name does not match"
        else:
            assert (
                getattr(user_credits_values[1], key) == value
            ), f"Key {key} does not match"
    assert (
        getattr(user_credits_values[1], "balance")
        == user_credits_multiple_wo_default[1]["cap"]
    )
    assert getattr(user_credits_values[1], "user_name") == user.name
    assert (
        getattr(user_credits_values[1], "user_options")
        == user_credits_multiple_wo_default[1]["user_options"]
    )


@pytest.mark.asyncio
async def test_credits_user_list_wo_default_multimatch(app, user):
    app.authenticator.credits_user = user_credits_multiple_wo_default_multimatch
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits_values = user_credits.credits_user_values
    assert user_credits_values is not None
    assert len(user_credits_values) == 2
    for key, value in user_credits_multiple_wo_default_multimatch[0].items():
        if key == "project":
            assert (
                getattr(user_credits_values[0], "project_name") == value["name"]
            ), "Key project/project_name does not match"
        else:
            assert (
                getattr(user_credits_values[0], key) == value
            ), f"Key {key} does not match"
    assert (
        getattr(user_credits_values[0], "balance")
        == user_credits_multiple_wo_default_multimatch[0]["cap"]
    )
    assert getattr(user_credits_values[0], "user_name") == user.name
    assert (
        getattr(user_credits_values[0], "user_options")
        == user_credits_multiple_wo_default_multimatch[0]["user_options"]
    )

    for key, value in user_credits_multiple_wo_default_multimatch[1].items():
        if key == "project":
            assert (
                getattr(user_credits_values[1], "project_name") == value["name"]
            ), "Key project/project_name does not match"
        else:
            assert (
                getattr(user_credits_values[1], key) == value
            ), f"Key {key} does not match"
    assert (
        getattr(user_credits_values[1], "balance")
        == user_credits_multiple_wo_default_multimatch[1]["cap"]
    )
    assert getattr(user_credits_values[1], "user_name") == user.name
    assert (
        getattr(user_credits_values[1], "user_options")
        == user_credits_multiple_wo_default_multimatch[1]["user_options"]
    )


@pytest.mark.asyncio
async def test_credits_user_simple_func(app, user):
    app.authenticator.credits_user = user_credits_simple_function
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits_values = user_credits.credits_user_values
    assert user_credits_values is not None
    assert len(user_credits_values) == 1
    for key, value in user_credits_simple.items():
        assert getattr(user_credits_values[0], key) == value
    assert getattr(user_credits_values[0], "balance") == user_credits_simple["cap"]
    assert getattr(user_credits_values[0], "user_name") == user.name
    assert getattr(user_credits_values[0], "project_name") is None


@pytest.mark.asyncio
async def test_credits_user_simple_func_list(app, user):
    app.authenticator.credits_user = user_credits_simple_function_list
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits_values = user_credits.credits_user_values
    assert user_credits_values is not None
    assert len(user_credits_values) == 1
    for key, value in user_credits_simple.items():
        assert getattr(user_credits_values[0], key) == value
    assert getattr(user_credits_values[0], "balance") == user_credits_simple["cap"]
    assert getattr(user_credits_values[0], "user_name") == user.name
    assert getattr(user_credits_values[0], "project_name") is None


@pytest.mark.asyncio
async def test_credits_user_simple_asyncfunc(app, user):
    app.authenticator.credits_user = async_user_credits_simple_function
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits_values = user_credits.credits_user_values
    assert user_credits_values is not None
    assert len(user_credits_values) == 1
    for key, value in user_credits_simple.items():
        assert getattr(user_credits_values[0], key) == value
    assert getattr(user_credits_values[0], "balance") == user_credits_simple["cap"]
    assert getattr(user_credits_values[0], "user_name") == user.name
    assert getattr(user_credits_values[0], "project_name") is None


@pytest.mark.asyncio
async def test_credits_user_simple_asyncfunc_list(app, user):
    app.authenticator.credits_user = async_user_credits_simple_function_list
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits_values = user_credits.credits_user_values
    assert user_credits_values is not None
    assert len(user_credits_values) == 1
    for key, value in user_credits_simple.items():
        assert getattr(user_credits_values[0], key) == value
    assert getattr(user_credits_values[0], "balance") == user_credits_simple["cap"]
    assert getattr(user_credits_values[0], "user_name") == user.name
    assert getattr(user_credits_values[0], "project_name") is None


@pytest.mark.asyncio
async def test_credits_user_function_admin(app, user, admin_user):
    admin_added_cap = 150

    def user_credits_simple_function(_, username, groups, is_admin, auth_state):
        ret = copy.deepcopy(user_credits_simple)
        if is_admin:
            ret["cap"] += admin_added_cap
        return ret

    app.authenticator.credits_user = user_credits_simple_function
    await app.login_user(admin_user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, admin_user.name)
    assert (
        user_credits.credits_user_values[0].cap
        == user_credits_simple["cap"] + admin_added_cap
    )

    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    assert user_credits.credits_user_values[0].cap == user_credits_simple["cap"]


@pytest.mark.asyncio
async def test_credits_user_function_group(app, users, group):
    user1, user2 = users
    group.users.append(user1.orm_user)
    app.db.commit()
    group_added_cap = 7

    def user_credits_simple_function(_, username, groups, is_admin, auth_state):
        ret = copy.deepcopy(user_credits_simple)
        if group.name in groups:
            ret["cap"] += group_added_cap
        return ret

    app.authenticator.credits_user = user_credits_simple_function
    await app.login_user(user1.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user1.name)
    assert (
        user_credits.credits_user_values[0].cap
        == user_credits_simple["cap"] + group_added_cap
    )

    await app.login_user(user2.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user2.name)
    assert user_credits.credits_user_values[0].cap == user_credits_simple["cap"]


@pytest.mark.asyncio
async def test_credits_user_function_username_async(app, users):
    user1, user2 = users
    user1_added_cap = 25

    def user_credits_simple_function(_, username, groups, is_admin, auth_state):
        ret = copy.deepcopy(user_credits_simple)
        if username == user1.name:
            ret["cap"] += user1_added_cap
        return ret

    app.authenticator.credits_user = user_credits_simple_function
    await app.login_user(user1.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user1.name)
    assert (
        user_credits.credits_user_values[0].cap
        == user_credits_simple["cap"] + user1_added_cap
    )

    await app.login_user(user2.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user2.name)
    assert user_credits.credits_user_values[0].cap == user_credits_simple["cap"]


@pytest.mark.asyncio
async def test_credits_available_projects_user_project(app, users):

    user1, user2 = users

    def user_credits(_, username, groups, is_admin, auth_state):
        ret = copy.deepcopy(user_credits_simple)
        if username == user1.name:
            ret["project"] = {
                "name": "community1",
                "cap": 1000,
                "grant_interval": 600,
                "grant_value": 60,
            }
        elif username == user2.name:
            ret["project"] = {
                "name": "community2",
                "cap": 1000,
                "grant_interval": 600,
                "grant_value": 60,
            }
        return ret

    app.authenticator.credits_user = user_credits
    await app.login_user(user1.name)
    await app.login_user(user2.name)
    user_credits1 = CreditsUser.get_user(app.authenticator.parent.db, user1.name)
    assert user_credits1.credits_user_values[0].project.name == "community1"
    assert user_credits1.credits_user_values[0].project_name == "community1"

    user_credits2 = CreditsUser.get_user(app.authenticator.parent.db, user2.name)
    assert user_credits2.credits_user_values[0].project.name == "community2"
    assert user_credits2.credits_user_values[0].project_name == "community2"


@pytest.mark.asyncio
async def test_credits_available_projects_user_project_add_entry(app, user):
    return_all = False

    async def async_user_credits_runtime_change(
        _, username, groups, is_admin, auth_state
    ):
        if return_all:
            return user_credits_multiple_w_default
        else:
            return user_credits_multiple_w_default[0]

    app.authenticator.credits_user = async_user_credits_runtime_change
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    assert len(user_credits.credits_user_values) == 1
    assert user_credits.credits_user_values[0].project.name == "systemA"
    assert user_credits.credits_user_values[0].project_name == "systemA"

    return_all = True
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    assert len(user_credits.credits_user_values) == 2
    assert user_credits.credits_user_values[0].project.name == "systemA"
    assert user_credits.credits_user_values[0].project_name == "systemA"
    assert user_credits.credits_user_values[0].name == "systemA"
    assert user_credits.credits_user_values[1].name == "default"
    assert user_credits.credits_user_values[1].project is None
    assert user_credits.credits_user_values[1].project_name is None


@pytest.mark.asyncio
async def test_credits_available_projects_user_project_del_entry(app, user):
    return_all = True

    async def async_user_credits_runtime_change(
        _, username, groups, is_admin, auth_state
    ):
        if return_all:
            return user_credits_multiple_wo_default
        else:
            return user_credits_multiple_wo_default[-1]

    app.authenticator.credits_user = async_user_credits_runtime_change
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    assert len(user_credits.credits_user_values) == 2
    assert user_credits.credits_user_values[0].project.name == "systemA"
    assert user_credits.credits_user_values[0].project_name == "systemA"
    assert user_credits.credits_user_values[0].name == "systemA"
    assert user_credits.credits_user_values[1].name == "systemB"
    assert user_credits.credits_user_values[1].project.name == "systemB"
    assert user_credits.credits_user_values[1].project_name == "systemB"

    return_all = False
    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    assert len(user_credits.credits_user_values) == 1
    assert user_credits.credits_user_values[0].project.name == "systemB"
    assert user_credits.credits_user_values[0].project_name == "systemB"


@pytest.mark.asyncio
async def test_credits_task_post_hook_async_called(app):
    hook_called = []
    event = asyncio.Event()

    async def post_hook():
        hook_called.append(True)
        event.set()

    app.authenticator.credits_task_post_hook = post_hook
    await event.wait()

    assert hook_called, "Post-task hook was not executed"


@pytest.mark.asyncio
async def test_credits_task_post_hook_called(app):
    hook_called = []
    event = asyncio.Event()

    def post_hook():
        hook_called.append(True)
        event.set()

    app.authenticator.credits_task_post_hook = post_hook
    await event.wait()

    assert hook_called, "Post-task hook was not executed"
