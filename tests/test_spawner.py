"""Tests for CreditsAuthenticator / CreditsAuthenticator"""

import asyncio
import copy
import random
import string
from datetime import datetime, timedelta

import pytest
from jupyterhub.tests.test_spawner import wait_for_spawner
from jupyterhub.utils import utcnow

from jupyterhub_credit_service.orm import ProjectCredits as ORMProjectCredits
from jupyterhub_credit_service.orm import UserCredits as ORMUserCredits
from jupyterhub_credit_service.spawner import CreditsException

from .test_auth import available_projects


def get_proj_name():
    proj_name = "".join(random.choice(string.ascii_lowercase) for i in range(8))
    return proj_name


def get_projects(proj_name):
    ret = copy.deepcopy(available_projects)
    ret[0]["name"] = proj_name
    return ret


@pytest.mark.asyncio
async def test_spawner_first_bill(db, app, user):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    event.clear()
    call_counter = []
    await event.wait()

    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.balance == 90, f"Credits value: {user_credits.balance}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

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

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    event.clear()
    call_counter = []
    await event.wait()

    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.balance == 90, f"Credits value: {user_credits.balance}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Stop Server
    save_billing_interval = spawner._billing_interval
    await user.stop()
    status = await spawner.poll()
    assert status == 0

    app.authenticator.db_session.refresh(user_credits)
    after_stop_balance = user_credits.balance

    await asyncio.sleep(save_billing_interval)

    # Wait for next billing run
    event.clear()
    await event.wait()
    app.authenticator.db_session.refresh(user_credits)
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

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    event.clear()
    await event.wait()

    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.balance == 90, f"Credits value First: {user_credits.balance}"
    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Wait until the spawner must be billed again
    app.authenticator.db_session.refresh(user_credits)
    last_spawner_bill = user_credits.spawner_bills[str(spawner.orm_spawner.id)]
    next_spawner_bill = datetime.fromisoformat(last_spawner_bill) + timedelta(
        seconds=spawner._billing_interval
    )
    now = utcnow(with_tz=False)
    to_wait = (next_spawner_bill - now).total_seconds()
    await asyncio.sleep(to_wait)

    # Wait for next billing run
    event.clear()
    await event.wait()

    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.balance == 80, f"Credits value Second: {user_credits.balance}"

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

    proj_name = get_proj_name()

    def user_project(username, *args):
        if username == user.name:
            return proj_name
        return None

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1
    app.authenticator.credits_available_projects = get_projects(proj_name)
    app.authenticator.credits_user_project = user_project

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    event.clear()
    await event.wait()

    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.balance == 100, f"Credits value First: {user_credits.balance}"

    proj_credits = (
        app.authenticator.db_session.query(ORMProjectCredits)
        .filter(ORMProjectCredits.name == proj_name)
        .first()
    )
    assert (
        proj_credits.balance == proj_credits.cap - spawner._billing_value
    ), f"Proj Credits value First: {proj_credits.balance} != {proj_credits.cap} - {spawner._billing_value}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Wait until the spawner must be billed again
    app.authenticator.db_session.refresh(user_credits)
    last_spawner_bill = user_credits.spawner_bills[str(spawner.orm_spawner.id)]
    next_spawner_bill = datetime.fromisoformat(last_spawner_bill) + timedelta(
        seconds=spawner._billing_interval
    )
    now = utcnow(with_tz=False)
    to_wait = (next_spawner_bill - now).total_seconds()
    await asyncio.sleep(to_wait)

    # Wait for next billing run
    event.clear()
    await event.wait()

    app.authenticator.db_session.refresh(user_credits)
    assert user_credits.balance == 100, f"Credits value Second: {user_credits.balance}"

    app.authenticator.db_session.refresh(proj_credits)
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

    proj_name = get_proj_name()

    def user_project(username, *args):
        if username == user.name:
            return proj_name
        return None

    available_projects_ = get_projects(proj_name)
    available_projects_[0]["cap"] = 7
    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1
    app.authenticator.credits_available_projects = available_projects_
    app.authenticator.credits_user_project = user_project

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    event.clear()
    await event.wait()

    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    proj_credits = (
        app.authenticator.db_session.query(ORMProjectCredits)
        .filter(ORMProjectCredits.name == proj_name)
        .first()
    )

    user_to_pay = spawner._billing_value - user_credits.project.cap
    assert (
        proj_credits.balance == 0
    ), f"Proj Credits value First: {proj_credits.balance} != 0"
    assert (
        user_credits.balance == user_credits.cap - user_to_pay
    ), f"Credits value First: {user_credits.balance} != {user_credits.cap} - ({spawner._billing_value} - {user_credits.project.cap})"

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

    proj_name = get_proj_name()

    def user_project(username, *args):
        if username == user.name:
            return proj_name
        return None

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1
    app.authenticator.credits_available_projects = get_projects(proj_name)
    app.authenticator.credits_user_project = user_project

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    event.clear()
    await event.wait()

    app.authenticator.db_session.refresh(user_credits)
    assert user_credits.balance == 100, f"Credits value First: {user_credits.balance}"

    proj_credits = (
        app.authenticator.db_session.query(ORMProjectCredits)
        .filter(ORMProjectCredits.name == proj_name)
        .first()
    )
    assert (
        proj_credits.balance == proj_credits.cap - spawner._billing_value
    ), f"Proj Credits value First: {proj_credits.balance} != {proj_credits.cap} - {spawner._billing_value}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Wait until the spawner must be billed again
    app.authenticator.db_session.refresh(user_credits)
    last_spawner_bill = user_credits.spawner_bills[str(spawner.orm_spawner.id)]
    next_spawner_bill = datetime.fromisoformat(last_spawner_bill) + timedelta(
        seconds=spawner._billing_interval
    )
    now = utcnow(with_tz=False)
    to_wait = (next_spawner_bill - now).total_seconds()
    await asyncio.sleep(to_wait)

    # Wait for next billing run
    event.clear()
    await event.wait()

    app.authenticator.db_session.refresh(user_credits)
    assert user_credits.balance == 100, f"Credits value Second: {user_credits.balance}"

    app.authenticator.db_session.refresh(proj_credits)
    expected_credits_after_first_run = proj_credits.cap - 2 * spawner._billing_value
    assert (
        proj_credits.balance == expected_credits_after_first_run
    ), f"Proj Credits value First: {proj_credits.balance} != {proj_credits.cap} - {2*spawner._billing_value}"

    # Stop Server
    save_billing_interval = spawner._billing_interval
    save_billing_value = spawner._billing_value
    app.log.info("++++++++++++++ Stop Server")
    await user.stop()
    status = await spawner.poll()
    assert status == 0
    app.log.info("++++++++++++++ Stopped Server")

    # Save current balance to use as reference for second start
    app.authenticator.db_session.refresh(proj_credits)
    save_proj_credits_balance = proj_credits.balance

    # Let's wait billing_interval seconds before starting again
    await asyncio.sleep(save_billing_interval)

    # Wait for next billing run
    event.clear()
    await event.wait()

    app.authenticator.db_session.refresh(user_credits)
    app.authenticator.db_session.refresh(proj_credits)
    assert (
        proj_credits.balance == save_proj_credits_balance
    ), f"Proj Credits value First: {proj_credits.balance} != {proj_credits.cap} - {2*save_billing_value}"

    # Restart Spawner, see if we get billed correctly

    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    event.clear()
    await event.wait()

    # Assert first bill on second run
    app.authenticator.db_session.refresh(user_credits)
    app.authenticator.db_session.refresh(proj_credits)
    assert user_credits.balance == 100, f"Credits value First: {user_credits.balance}"
    assert (
        proj_credits.balance == save_proj_credits_balance - spawner._billing_value
    ), f"Proj Credits value First: {proj_credits.balance} != {save_proj_credits_balance} - {spawner._billing_value}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Wait until the spawner must be billed again
    app.authenticator.db_session.refresh(user_credits)
    last_spawner_bill = user_credits.spawner_bills[str(spawner.orm_spawner.id)]
    next_spawner_bill = datetime.fromisoformat(last_spawner_bill) + timedelta(
        seconds=spawner._billing_interval
    )
    now = utcnow(with_tz=False)
    to_wait = (next_spawner_bill - now).total_seconds()
    await asyncio.sleep(to_wait)

    # Wait for next billing run
    event.clear()
    await event.wait()

    # Asset second bill for second run
    app.authenticator.db_session.refresh(user_credits)
    app.authenticator.db_session.refresh(proj_credits)
    assert user_credits.balance == 100, f"Credits value Second: {user_credits.balance}"
    expected_credits_after_second_run = (
        save_proj_credits_balance - 2 * spawner._billing_value
    )
    assert (
        proj_credits.balance == expected_credits_after_second_run
    ), f"Proj Credits value First: {proj_credits.balance} != {save_proj_credits_balance} - {2*spawner._billing_value}"

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

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.billing_value = 150
    spawner.cmd = ["jupyterhub-singleuser"]
    with pytest.raises(CreditsException) as exc_info:
        await user.spawn()
        assert "Not enough credits" in str(exc_info.value)
        assert "Current User credits" in str(exc_info.value)
        assert "project" not in str(exc_info.value)

    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.balance == 100, f"Credits value: {user_credits.balance}"

    status = await spawner.poll()
    assert status == 0


async def test_spawner_proj_to_expensive(db, app, user):
    call_counter = []
    event = asyncio.Event()

    async def post_hook():
        call_counter.append(1)
        event.set()

    proj_name = get_proj_name()

    def user_project(username, *args):
        if username == user.name:
            return proj_name
        return None

    available_projects_ = get_projects(proj_name)
    available_projects_[0]["cap"] = 7
    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1
    app.authenticator.credits_available_projects = available_projects_
    app.authenticator.credits_user_project = user_project

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.billing_value = 150
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

    proj_name = get_proj_name()

    def user_project(username, *args):
        if username == user.name:
            return proj_name
        return None

    available_projects_ = get_projects(proj_name)
    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 1
    app.authenticator.credits_available_projects = available_projects_
    app.authenticator.credits_user_project = user_project

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.billing_value = 150
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    event.clear()
    call_counter = []
    await event.wait()

    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    proj_credits = user_credits.project
    assert user_credits.balance == 100, f"Credits value: {user_credits.balance}"
    assert (
        proj_credits.balance == proj_credits.cap - spawner._billing_value
    ), f"Project Credits value: {proj_credits.balance} != {proj_credits.cap} - {spawner._billing_value}"
    assert proj_credits.balance < 1000

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

    app.authenticator.credits_task_post_hook = post_hook
    app.authenticator.credits_task_interval = 10

    await app.login_user(user.name)
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert user_credits.cap == 100
    assert user_credits.balance == 100
    spawner = user.spawner
    spawner.billing_value = 80
    spawner.billing_interval = 8
    spawner.cmd = ["jupyterhub-singleuser"]
    await user.spawn()
    assert spawner.server.ip == "127.0.0.1"
    assert spawner.server.port > 0
    await wait_for_spawner(spawner)

    # Now the spawner is running. Let's clear the event and wait for another billing run
    event.clear()
    call_counter = []
    await event.wait()

    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert (
        user_credits.balance == user_credits.cap - spawner.billing_value
    ), f"Credits value: {user_credits.balance}"

    # Check if it's running
    status = await spawner.poll()
    assert status is None

    # Wait for next two billing runs.
    event.clear()
    await event.wait()
    event.clear()
    await event.wait()

    # Check if it's no longer running
    status = await spawner.poll()
    assert status == 0
