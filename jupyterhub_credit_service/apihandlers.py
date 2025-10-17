from jupyterhub.apihandlers.base import APIHandler
from jupyterhub.scopes import needs_scope
from tornado.web import HTTPError, authenticated

from .orm import ProjectCredits, UserCredits

background_task = None
import json


class CreditsAPIHandler(APIHandler):
    @authenticated
    async def get(self):
        user = await self.get_current_user()
        if not user:
            raise HTTPError(403, "Not authenticated")

        if not user.authenticator.credits_enabled:
            raise HTTPError(404, "Credits function is currently disabled")

        user_credits = (
            user.authenticator.db_session.query(UserCredits)
            .filter(UserCredits.name == user.name)
            .first()
        )

        if not user_credits:
            # Create entry for user with default values
            raise HTTPError(404, "No credit entry found for user")

        model = {
            "user_id": user.id,
            "balance": user_credits.balance,
            "cap": user_credits.cap,
            "grant_value": user_credits.grant_value,
            "grant_interval": user_credits.grant_interval,
            "grant_last_update": user_credits.grant_last_update.isoformat(),
        }
        project = user_credits.project
        if project:
            project_model = {
                "name": project.name,
                "balance": project.balance,
                "cap": project.cap,
                "grant_value": project.grant_value,
                "grant_interval": project.grant_interval,
                "grant_last_update": project.grant_last_update.isoformat(),
            }
            model.update({"project": project_model})

        self.write(json.dumps(model))


class CreditsUserAPIHandler(APIHandler):
    @needs_scope("admin:users")
    async def post(self, user_name):
        user = self.find_user(user_name)
        if not user:
            raise HTTPError(404, "User not found")
        data = self.get_json_body()
        credits = (
            user.authenticator.db_session.query(UserCredits)
            .filter(UserCredits.name == user.name)
            .first()
        )
        if not credits:
            # Create entry for user with default values
            raise HTTPError(404, "No credit entry found for user")
        balance = data.get("balance", None)
        cap = data.get("cap", None)
        grant_value = data.get("grant_value", None)
        grant_interval = data.get("grant_interval", None)
        project_name = data.get("project_name", None)

        if balance and cap and balance > cap:
            raise HTTPError(
                400, f"Balance can't be bigger than cap ({balance} / {cap})"
            )
        if balance and balance > credits.cap:
            raise HTTPError(
                400, f"Balance can't be bigger than cap ({balance} / {credits.cap})"
            )
        if balance and balance < 0:
            raise HTTPError(400, "Balance can't be negative")
        if balance:
            credits.balance = balance
        if cap:
            credits.cap = cap
        if grant_value:
            credits.grant_value = grant_value
        if grant_interval:
            credits.grant_interval = grant_interval
        if project_name:
            project = (
                user.authenticator.db_session.query(ProjectCredits)
                .filter(ProjectCredits.name == project_name)
                .first()
            )
            if not project:
                raise HTTPError(404, f"Unknown project {project_name}.")
            credits.project = project
        user.authenticator.db_session.add(credits)
        user.authenticator.db_session.commit()
        self.set_status(200)


class CreditsProjectAPIHandler(APIHandler):
    @needs_scope("admin:users")
    async def post(self, project_name):
        data = self.get_json_body()
        balance = data.get("balance", None)
        cap = data.get("cap", None)
        grant_value = data.get("grant_value", None)
        grant_interval = data.get("grant_interval", None)

        project = (
            self.current_user.authenticator.db_session.query(ProjectCredits)
            .filter(ProjectCredits.name == project_name)
            .first()
        )

        if not project:
            raise HTTPError(404, f"Unknown project {project_name}.")

        if balance and cap and balance > cap:
            raise HTTPError(
                400, f"Balance can't be bigger than cap ({balance} / {cap})"
            )
        if balance and balance > project.cap:
            raise HTTPError(
                400, f"Balance can't be bigger than cap ({balance} / {project.cap})"
            )
        if balance and balance < 0:
            raise HTTPError(400, "Balance can't be negative")
        if balance:
            project.balance = balance
        if cap:
            project.cap = cap
        if grant_value:
            project.grant_value = grant_value
        if grant_interval:
            project.grant_interval = grant_interval
        self.current_user.authenticator.db_session.commit()
        self.set_status(200)
