import copy
import json

from jupyterhub.tests.utils import (
    api_request,
    async_requests,
    public_url,
)

from jupyterhub_credit_service.orm import CreditsUser

from .test_auth import user_credits_simple, user_credits_simple_project
from .test_spawner import get_proj_name


async def test_credits_not_authenticated_redirect_login(app):
    url = public_url(app, path="hub/api/credits")
    r = await async_requests.get(url)
    assert "/hub/login" in r.url
    assert r.status_code == 200


async def test_credits_auth(app, user):
    app.authenticator.credits_user = user_credits_simple
    await app.login_user(user.name)
    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    assert len(resp) > 0
    resp = resp[0]
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    app.authenticator.parent.db.refresh(credits_user)
    credits_user_values = credits_user.credits_user_values[0]
    assert resp["name"] == credits_user_values.name
    assert resp["balance"] == credits_user_values.balance
    assert resp["cap"] == credits_user_values.cap
    assert resp["grant_interval"] == credits_user_values.grant_interval
    assert resp["grant_value"] == credits_user_values.grant_value
    assert (
        resp["grant_last_update"] == credits_user_values.grant_last_update.isoformat()
    )
    assert "project" not in resp.keys()


async def test_credits_auth_proj(app, user):
    proj_name = get_proj_name()
    local_user_credits_simple_project = copy.deepcopy(user_credits_simple_project)
    local_user_credits_simple_project["project"]["name"] = proj_name

    def user_credits_f(_, username, *args):
        if username == user.name:
            return local_user_credits_simple_project
        return user_credits_simple

    app.authenticator.credits_user = user_credits_f
    await app.login_user(user.name)

    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    assert len(resp) > 0
    resp = resp[0]
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    app.authenticator.parent.db.refresh(credits_user)
    credits_user_values = credits_user.credits_user_values[0]
    assert resp["name"] == credits_user_values.name
    assert resp["project"]["name"] == credits_user_values.project_name
    assert resp["project"]["balance"] == credits_user_values.project.balance
    assert resp["project"]["cap"] == credits_user_values.project.cap
    assert (
        resp["project"]["grant_interval"] == credits_user_values.project.grant_interval
    )
    assert resp["project"]["grant_value"] == credits_user_values.project.grant_value
    assert (
        resp["project"]["grant_last_update"]
        == credits_user_values.project.grant_last_update.isoformat()
    )


async def test_credits_admin_user_update(app, user):
    app.authenticator.credits_user = user_credits_simple
    await app.login_user(user.name)
    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    app.authenticator.parent.db.refresh(credits_user)
    user_credits = credits_user.credits_user_values[0]
    assert resp[0]["balance"] == user_credits.balance

    new_balance = user_credits.balance - 30
    data = {"balance": new_balance}
    r = await api_request(
        app,
        f"credits/user/{user.name}/{user_credits.name}",
        data=json.dumps(data),
        method="post",
    )
    assert r.status_code == 200
    app.authenticator.parent.db.refresh(user_credits)
    assert user_credits.balance == new_balance


async def test_credits_admin_user_403(app, user):
    app.authenticator.credits_user = user_credits_simple
    await app.login_user(user.name)
    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    app.authenticator.parent.db.refresh(credits_user)
    user_credits = credits_user.credits_user_values[0]
    assert resp[0]["balance"] == user_credits.balance

    new_balance = user_credits.balance - 30
    data = {"balance": new_balance}
    r = await api_request(
        app,
        f"credits/user/{user.name}/{user_credits.name}",
        data=json.dumps(data),
        method="post",
        headers={"Authorization": "token " + token},
    )
    assert r.status_code == 403


async def test_credits_admin_proj_update(app, user):
    proj_name = get_proj_name()
    local_user_credits_simple_project = copy.deepcopy(user_credits_simple_project)
    local_user_credits_simple_project["project"]["name"] = proj_name

    def user_credits_f(_, username, *args):
        if username == user.name:
            return local_user_credits_simple_project
        return user_credits_simple

    app.authenticator.credits_user = user_credits_f
    await app.login_user(user.name)

    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    user_credits = credits_user.credits_user_values[0]
    assert resp[0]["project"]["balance"] == user_credits.project.balance

    new_balance = user_credits.project.balance - 30
    data = {"balance": new_balance}
    r = await api_request(
        app, f"credits/project/{proj_name}", data=json.dumps(data), method="post"
    )
    assert r.status_code == 200
    app.authenticator.parent.db.refresh(user_credits)
    assert user_credits.project.balance == new_balance


async def test_credits_admin_proj_403(app, user):
    proj_name = get_proj_name()
    local_user_credits_simple_project = copy.deepcopy(user_credits_simple_project)
    local_user_credits_simple_project["project"]["name"] = proj_name

    def user_credits_f(_, username, *args):
        if username == user.name:
            return local_user_credits_simple_project
        return user_credits_simple

    app.authenticator.credits_user = user_credits_f
    await app.login_user(user.name)

    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    credits_user = CreditsUser.get_user(app.authenticator.parent.db, user.name)
    app.authenticator.parent.db.refresh(credits_user)
    user_credits = credits_user.credits_user_values[0]
    assert resp[0]["project"]["balance"] == user_credits.project.balance

    new_balance = user_credits.project.balance - 30
    data = {"balance": new_balance}
    r = await api_request(
        app,
        f"credits/project/{proj_name}",
        data=json.dumps(data),
        method="post",
        headers={"Authorization": "token " + token},
    )
    assert r.status_code == 403
