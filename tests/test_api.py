import json

from jupyterhub.tests.utils import (
    api_request,
    async_requests,
    public_url,
)

from jupyterhub_credit_service.orm import UserCredits as ORMUserCredits

from .test_spawner import get_proj_name, get_projects


async def test_credits_not_authenticated_redirect_login(app):
    url = public_url(app, path="hub/api/credits")
    r = await async_requests.get(url)
    assert "/hub/login" in r.url
    assert r.status_code == 200


async def test_credits_auth(app, user):
    await app.login_user(user.name)
    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert resp["balance"] == user_credits.balance
    assert resp["cap"] == user_credits.cap
    assert resp["grant_interval"] == user_credits.grant_interval
    assert resp["grant_value"] == user_credits.grant_value
    assert resp["grant_last_update"] == user_credits.grant_last_update.isoformat()
    assert "project" not in resp.keys()


async def test_credits_auth_proj(app, user):
    proj_name = get_proj_name()

    def user_project(username, *args):
        if username == user.name:
            return proj_name
        return None

    app.authenticator.credits_available_projects = get_projects(proj_name)
    app.authenticator.credits_user_project = user_project
    await app.login_user(user.name)

    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert resp["project"]["name"] == user_credits.project_name
    assert resp["project"]["balance"] == user_credits.project.balance
    assert resp["project"]["cap"] == user_credits.project.cap
    assert resp["project"]["grant_interval"] == user_credits.project.grant_interval
    assert resp["project"]["grant_value"] == user_credits.project.grant_value
    assert (
        resp["project"]["grant_last_update"]
        == user_credits.project.grant_last_update.isoformat()
    )


async def test_credits_admin_user_update(app, user):
    await app.login_user(user.name)
    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert resp["balance"] == user_credits.balance

    new_balance = user_credits.balance - 30
    data = {"balance": new_balance}
    r = await api_request(
        app, f"credits/user/{user.name}", data=json.dumps(data), method="post"
    )
    assert r.status_code == 200
    app.authenticator.db_session.refresh(user_credits)
    assert user_credits.balance == new_balance


async def test_credits_admin_user_403(app, user):
    await app.login_user(user.name)
    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert resp["balance"] == user_credits.balance

    new_balance = user_credits.balance - 30
    data = {"balance": new_balance}
    r = await api_request(
        app,
        f"credits/user/{user.name}",
        data=json.dumps(data),
        method="post",
        headers={"Authorization": "token " + token},
    )
    assert r.status_code == 403


async def test_credits_admin_proj_update(app, user):
    proj_name = get_proj_name()

    def user_project(username, *args):
        if username == user.name:
            return proj_name
        return None

    app.authenticator.credits_available_projects = get_projects(proj_name)
    app.authenticator.credits_user_project = user_project
    await app.login_user(user.name)

    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert resp["project"]["balance"] == user_credits.project.balance

    new_balance = user_credits.project.balance - 30
    data = {"balance": new_balance}
    r = await api_request(
        app, f"credits/project/{proj_name}", data=json.dumps(data), method="post"
    )
    assert r.status_code == 200
    app.authenticator.db_session.refresh(user_credits)
    assert user_credits.project.balance == new_balance


async def test_credits_admin_proj_403(app, user):
    proj_name = get_proj_name()

    def user_project(username, *args):
        if username == user.name:
            return proj_name
        return None

    app.authenticator.credits_available_projects = get_projects(proj_name)
    app.authenticator.credits_user_project = user_project
    await app.login_user(user.name)

    token = user.new_api_token()

    r = await api_request(app, "credits", headers={"Authorization": "token " + token})
    assert r.status_code == 200
    resp = r.json()
    user_credits = (
        app.authenticator.db_session.query(ORMUserCredits)
        .filter(ORMUserCredits.name == user.name)
        .first()
    )
    assert resp["project"]["balance"] == user_credits.project.balance

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
