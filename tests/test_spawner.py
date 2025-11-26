"""Tests for CreditsAuthenticator / CreditsAuthenticator"""

import asyncio
import copy
import random
import string
from datetime import datetime, timedelta

import pytest
from jupyterhub.tests.test_spawner import wait_for_spawner
from jupyterhub.tests.utils import api_request
from jupyterhub.utils import utcnow

from jupyterhub_credit_service.orm import CreditsUser
from jupyterhub_credit_service.spawner import CreditsException

from .test_auth import user_credits_simple


def get_proj_name(new_username=None, *args, **kwargs):
    proj_name = "".join(random.choice(string.ascii_lowercase) for i in range(8))
    if new_username:
        proj_name = f"{new_username}-{proj_name}"
    return proj_name


@pytest.mark.asyncio
async def test_spawner_first_bill(db, app, user):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1
    app.authenticator.credits_user = user_credits_simple

    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(
        app.authenticator.parent.db, user.name
    ).credits_user_values[0]
    assert user_credits.cap == user_credits_simple["cap"]
    assert user_credits.balance == user_credits_simple["cap"]
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    call_counter = []
    await event.wait()

    app.authenticator.parent.db.refresh(user_credits)
    assert len(call_counter) >= 1, f"Call counter: {call_counter}"
    assert (
        user_credits.balance != user_credits_simple["cap"]
    ), f"Credits value: {user_credits.balance}"
    assert (
        user_credits.balance == user_credits_simple["cap"] - spawner._billing_value
    ), f"Credits value: {user_credits.balance} != {user_credits_simple['cap']} - {spawner._billing_value}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Stop Server
    await user.stop()
    status = await spawner.poll()
    assert status == 0


@pytest.mark.asyncio
async def test_spawner_refresh_credits_pre_spawn(db, app, user, mocker):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    # Spy on the target function before it’s called
    spy_update = mocker.AsyncMock(wraps=app.authenticator.update_user_credit)
    mocker.patch.object(app.authenticator, "update_user_credit", spy_update)

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 60
    app.authenticator.credits_user = user_credits_simple
    app.authenticator.refresh_pre_spawn = True

    await app.login_user(user.name)
    user_credits = CreditsUser.get_user(
        app.authenticator.parent.db, user.name
    ).credits_user_values[0]
    assert user_credits.cap == user_credits_simple["cap"]
    assert user_credits.balance == user_credits_simple["cap"]
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]

    prev_count = spy_update.await_count
    await api_request(app, f"users/{user.name}/server", method="post", name=user.name)
    assert spy_update.await_count == prev_count + 1

    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0

    await wait_for_spawner(spawner)

    # Stop Server
    await user.stop()
    status = await spawner.poll()
    assert status == 0


async def test_spawner_stopped_labs_not_billed(db, app, user):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1
    app.authenticator.credits_user = user_credits_simple
    app.db.refresh(user)
    await app.login_user(user.name)
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits = credits_user.credits_user_values[0]

    assert user_credits.cap == user_credits_simple["cap"]
    assert user_credits.balance == user_credits_simple["cap"]
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    call_counter = []
    await event.wait()

    app.authenticator.parent.db.refresh(user_credits)
    assert len(call_counter) >= 1, f"Call counter: {call_counter}"
    assert (
        user_credits.balance != user_credits_simple["cap"]
    ), f"Credits value: {user_credits.balance}"
    assert (
        user_credits.balance == user_credits_simple["cap"] - spawner._billing_value
    ), f"Credits value: {user_credits.balance} != {user_credits_simple['cap']} - {spawner._billing_value}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Stop Server
    save_billing_interval = spawner._billing_interval
    await user.stop()
    status = await spawner.poll()
    assert status == 0

    app.authenticator.parent.db.refresh(user_credits)
    after_stop_balance = user_credits.balance

    await asyncio.sleep(save_billing_interval)

    # Wait for next billing run
    await event.wait()
    app.authenticator.parent.db.refresh(user_credits)
    assert (
        after_stop_balance == user_credits.balance
    ), f"{after_stop_balance} not equal {user_credits.balance}"


async def test_spawner_second_bill(db, app, user):
    # In this test we're starting a Spawner with costs of 10 credits every 10 seconds.
    # Test if it was billed twice after 10-20 seconds
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1
    app.authenticator.credits_user = user_credits_simple

    await app.login_user(user.name)
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    credits_user_values = credits_user.credits_user_values[0]
    assert credits_user_values.cap == user_credits_simple["cap"]
    assert credits_user_values.balance == user_credits_simple["cap"]
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    call_counter = []
    await event.wait()

    app.authenticator.parent.db.refresh(credits_user_values)
    assert len(call_counter) >= 1, f"Call counter: {call_counter}"
    assert (
        credits_user_values.balance != user_credits_simple["cap"]
    ), f"Credits value: {credits_user_values.balance}"
    assert (
        credits_user_values.balance
        == user_credits_simple["cap"] - spawner._billing_value
    ), f"Credits value: {credits_user_values.balance} != {user_credits_simple['cap']} - {spawner._billing_value}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Wait until the spawner must be billed again
    app.authenticator.parent.db.refresh(credits_user)
    last_spawner_bill = credits_user.spawner_bills[str(spawner.orm_spawner.id)]
    next_spawner_bill = datetime.fromisoformat(last_spawner_bill) + timedelta(
        seconds=spawner._billing_interval
    )
    now = utcnow(with_tz=False)
    to_wait = (next_spawner_bill - now).total_seconds()
    await asyncio.sleep(to_wait)

    # Wait for next billing run
    await user.authenticator.credits_task_event.wait()

    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance
        == user_credits_simple["cap"] - 2 * spawner._billing_value
    ), f"Credits value: {credits_user_values.balance} != {user_credits_simple['cap']} - 2 * {spawner._billing_value}"

    # Stop Server
    await user.stop()
    status = await spawner.poll()
    assert status == 0


async def test_spawner_proj_billed(db, app, user):
    # In this test we're starting a Spawner with costs of 10 credits every 10 seconds.
    # Test if it was billed twice after 10-20 seconds
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    proj_name = get_proj_name()
    proj_values = {
        "name": proj_name,
        "cap": 1000,
        "grant_interval": 600,
        "grant_value": 60,
    }

    def user_credits(_, username, *args):
        ret = copy.deepcopy(user_credits_simple)
        if username == user.name:
            ret["project"] = proj_values
        return ret

    app.authenticator.credits_user = user_credits

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1
    # app.authenticator.credits_available_projects = get_projects(proj_name)
    # app.authenticator.credits_user_project = user_project

    await app.login_user(user.name)
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    credits_user_values = credits_user.credits_user_values[0]
    assert credits_user_values.cap == user_credits_simple["cap"]
    assert credits_user_values.balance == user_credits_simple["cap"]
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    await event.wait()

    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance == user_credits_simple["cap"]
    ), f"Credits value First: {credits_user_values.balance} != {user_credits_simple['cap']}  "

    proj_credits = credits_user_values.project
    assert proj_credits is not None, "No project credits found"
    assert (
        proj_credits.balance == proj_credits.cap - spawner._billing_value
    ), f"Proj Credits value First: {proj_credits.balance} != {proj_credits.cap} - {spawner._billing_value}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Wait until the spawner must be billed again
    app.authenticator.parent.db.refresh(credits_user)
    last_spawner_bill = credits_user.spawner_bills[str(spawner.orm_spawner.id)]
    next_spawner_bill = datetime.fromisoformat(last_spawner_bill) + timedelta(
        seconds=spawner._billing_interval
    )
    now = utcnow(with_tz=False)
    to_wait = (next_spawner_bill - now).total_seconds()
    await asyncio.sleep(to_wait)

    # Wait for next billing run
    await event.wait()

    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance == user_credits_simple["cap"]
    ), f"Credits value Second: {credits_user_values.balance} != {user_credits_simple['cap']}"

    app.authenticator.parent.db.refresh(proj_credits)
    assert (
        proj_credits.balance == proj_credits.cap - 2 * spawner._billing_value
    ), f"Proj Credits value First: {proj_credits.balance} != {proj_credits.cap} - {2*spawner._billing_value}"

    # Stop Server
    await user.stop()
    status = await spawner.poll()
    assert status == 0


async def test_spawner_proj_billed_partly(db, app, user):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    proj_name = get_proj_name()
    proj_values = {
        "name": proj_name,
        "cap": 3,
        "grant_interval": 600,
        "grant_value": 60,
    }

    def user_credits(_, username, *args):
        ret = copy.deepcopy(user_credits_simple)
        if username == user.name:
            ret["project"] = proj_values
        return ret

    app.authenticator.credits_user = user_credits

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1

    await app.login_user(user.name)
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    credits_user_values = credits_user.credits_user_values[0]
    assert credits_user_values.cap == user_credits_simple["cap"]
    assert credits_user_values.balance == user_credits_simple["cap"]
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    await event.wait()

    app.authenticator.parent.db.refresh(credits_user)

    user_to_pay = spawner._billing_value - credits_user_values.project.cap
    assert (
        credits_user_values.project.balance == 0
    ), f"Proj Credits value First: {credits_user_values.project.balance} != 0"
    assert (
        credits_user_values.balance == credits_user_values.cap - user_to_pay
    ), f"Credits value First: {credits_user_values.balance} != {credits_user_values.cap} - ({spawner._billing_value} - {credits_user_values.project.cap})"

    # Stop Server
    await user.stop()
    status = await spawner.poll()
    assert status == 0


async def test_spawner_proj_billed_start_stop_start(db, app, user):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    proj_name = get_proj_name()
    proj_values = {
        "name": proj_name,
        "cap": 100,
        "grant_interval": 600,
        "grant_value": 60,
    }

    def user_credits(_, username, *args):
        ret = copy.deepcopy(user_credits_simple)
        if username == user.name:
            ret["project"] = proj_values
        return ret

    app.authenticator.credits_user = user_credits

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1

    await app.login_user(user.name)
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    credits_user_values = credits_user.credits_user_values[0]
    assert credits_user_values.cap == user_credits_simple["cap"]
    assert credits_user_values.balance == user_credits_simple["cap"]
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    await event.wait()

    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance == user_credits_simple["cap"]
    ), f"Credits value First: {credits_user_values.balance} != {user_credits_simple['cap']}  "

    assert (
        credits_user_values.project.balance
        == credits_user_values.project.cap - spawner._billing_value
    ), f"Proj Credits value First: {credits_user_values.project.balance} != {credits_user_values.project.cap} - {spawner._billing_value}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Wait until the spawner must be billed again
    app.authenticator.parent.db.refresh(credits_user)
    last_spawner_bill = credits_user.spawner_bills[str(spawner.orm_spawner.id)]
    next_spawner_bill = datetime.fromisoformat(last_spawner_bill) + timedelta(
        seconds=spawner._billing_interval
    )
    now = utcnow(with_tz=False)
    to_wait = (next_spawner_bill - now).total_seconds()
    await asyncio.sleep(to_wait)

    # Wait for next billing run
    await event.wait()

    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance == user_credits_simple["cap"]
    ), f"Credits value Second: {credits_user_values.balance} != {user_credits_simple['cap']} "

    expected_credits_after_first_run = (
        credits_user_values.project.cap - 2 * spawner._billing_value
    )
    assert (
        credits_user_values.project.balance == expected_credits_after_first_run
    ), f"Proj Credits value First: {credits_user_values.project.balance} != {credits_user_values.project.cap} - {2*spawner._billing_value}"

    # Stop Server
    save_billing_interval = spawner._billing_interval
    spawner._billing_value
    app.log.info("++++++++++++++ Stop Server")
    await user.stop()
    status = await spawner.poll()
    assert status == 0
    app.log.info("++++++++++++++ Stopped Server")

    # Save current balance to use as reference for second start
    app.authenticator.parent.db.refresh(credits_user)
    save_proj_credits_balance = credits_user_values.project.balance

    # Let's wait billing_interval seconds before starting again
    await asyncio.sleep(save_billing_interval)

    # Wait for next billing run
    await event.wait()

    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance == user_credits_simple["cap"]
    ), f"Credits value First: {credits_user_values.balance}"
    assert (
        credits_user_values.project.balance == save_proj_credits_balance
    ), f"Proj Credits value First: {credits_user_values.project.balance} != {save_proj_credits_balance}"

    # Restart Spawner, see if we get billed correctly

    assert credits_user_values.cap == user_credits_simple["cap"]
    assert credits_user_values.balance == user_credits_simple["cap"]
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    await event.wait()

    # Assert first bill on second run
    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance == user_credits_simple["cap"]
    ), f"Credits value Second: {credits_user_values.balance}"
    assert (
        credits_user_values.project.balance
        == save_proj_credits_balance - spawner._billing_value
    ), f"Proj Credits value Second: {credits_user_values.project.balance} != {save_proj_credits_balance} - {spawner._billing_value}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Wait until the spawner must be billed again
    app.authenticator.parent.db.refresh(credits_user)
    last_spawner_bill = credits_user.spawner_bills[str(spawner.orm_spawner.id)]
    next_spawner_bill = datetime.fromisoformat(last_spawner_bill) + timedelta(
        seconds=spawner._billing_interval
    )
    now = utcnow(with_tz=False)
    to_wait = (next_spawner_bill - now).total_seconds()
    await asyncio.sleep(to_wait)

    # Wait for next billing run
    await event.wait()

    # Asset second bill for second run
    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance == user_credits_simple["cap"]
    ), f"Credits value Second: {credits_user_values.balance}"
    expected_credits_after_second_run = (
        save_proj_credits_balance - 2 * spawner._billing_value
    )
    assert (
        credits_user_values.project.balance == expected_credits_after_second_run
    ), f"Proj Credits value Second: {credits_user_values.project.balance} != {save_proj_credits_balance} - {2*spawner._billing_value}"

    await user.stop()
    status = await spawner.poll()
    assert status == 0


@pytest.mark.asyncio
async def test_spawner_to_expensive(db, app, user):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    not_enough_credits = copy.deepcopy(user_credits_simple)
    not_enough_credits["cap"] = 3
    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1
    app.authenticator.credits_user = not_enough_credits

    await app.login_user(user.name)
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    credits_user_values = credits_user.credits_user_values[0]
    assert credits_user_values.cap == not_enough_credits["cap"]
    assert credits_user_values.balance == not_enough_credits["cap"]
    spawner = user.spawner
    spawner.billing_value = 150
    spawner.cmd = ["jupyterhub-singleuser"]
    with pytest.raises(CreditsException) as exc_info:
        await user.spawn()
        assert "Not enough credits" in str(exc_info.value)
        assert "Current User credits" in str(exc_info.value)
        assert "project" not in str(exc_info.value)

    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance == not_enough_credits["cap"]
    ), f"Credits value: {credits_user_values.balance} != {not_enough_credits['cap']}"

    status = await spawner.poll()
    assert status == 0


async def test_spawner_proj_to_expensive(db, app, user):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    proj_name = get_proj_name()
    proj_values = {
        "name": proj_name,
        "cap": 2,
        "grant_interval": 600,
        "grant_value": 60,
    }

    def user_credits(_, username, *args):
        ret = copy.deepcopy(user_credits_simple)
        if username == user.name:
            ret["project"] = proj_values
        return ret

    app.authenticator.credits_user = user_credits

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1

    await app.login_user(user.name)
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    credits_user_values = credits_user.credits_user_values[0]
    assert credits_user_values.cap == user_credits_simple["cap"]
    assert credits_user_values.balance == user_credits_simple["cap"]
    spawner = user.spawner
    spawner.billing_value = user_credits_simple["cap"] + proj_values["cap"] + 1
    spawner.cmd = ["jupyterhub-singleuser"]
    with pytest.raises(CreditsException) as exc_info:
        await user.spawn()
        assert "Not enough credits" in str(exc_info.value)
        assert "Current User credits" in str(exc_info.value)
        assert f"Current project ({proj_name}) credits" in str(exc_info.value)


async def test_spawner_proj_costs_more_than_usercredit(db, app, user):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    proj_name = get_proj_name()
    proj_values = {
        "name": proj_name,
        "cap": 1000,
        "grant_interval": 600,
        "grant_value": 60,
    }

    def user_credits(_, username, *args):
        ret = copy.deepcopy(user_credits_simple)
        if username == user.name:
            ret["project"] = proj_values
        return ret

    app.authenticator.credits_user = user_credits

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1

    await app.login_user(user.name)
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    credits_user_values = credits_user.credits_user_values[0]
    assert credits_user_values.cap == user_credits_simple["cap"]
    assert credits_user_values.balance == user_credits_simple["cap"]
    spawner = user.spawner
    spawner.billing_value = user_credits_simple["cap"] + 10
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    call_counter = []
    await event.wait()

    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance == user_credits_simple["cap"]
    ), f"Credits value: {credits_user_values.balance} != {user_credits_simple['cap']}  "
    assert (
        credits_user_values.project.balance
        == credits_user_values.project.cap - spawner._billing_value
    ), f"Project Credits value: {credits_user_values.project.balance} != {credits_user_values.project.cap} - {spawner._billing_value}"
    assert (
        credits_user_values.project.balance < proj_values["cap"]
    ), f"Project Credits value: {credits_user_values.project.balance} < {proj_values['cap']}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Stop Server
    await user.stop()
    status = await spawner.poll()
    assert status == 0


async def test_spawner_stopped_when_no_credits_left(db, app, user):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()
        await asyncio.sleep(0)
        event.clear()

    app.authenticator.credits_user = user_credits_simple

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 10

    await app.login_user(user.name)
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    credits_user_values = credits_user.credits_user_values[0]
    assert credits_user_values.cap == user_credits_simple["cap"]
    assert credits_user_values.balance == user_credits_simple["cap"]

    spawner = user.spawner
    spawner.billing_value = user_credits_simple["cap"] // 2 + 3
    spawner.billing_interval = 8
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    call_counter = []
    await app.authenticator.credits_task_event.wait()

    app.authenticator.parent.db.refresh(credits_user)
    assert (
        credits_user_values.balance
        == user_credits_simple["cap"] - spawner.billing_value
    ), f"Credits value: {credits_user_values.balance} != {user_credits_simple['cap']} - {spawner.billing_value}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Wait for next two billing runs.
    await event.wait()
    await asyncio.sleep(1)
    await event.wait()

    # Give it some time to stop
    await asyncio.sleep(1)
    await event.wait()

    # Check if it's no longer running
    status = await spawner.poll()
    assert status == 0
