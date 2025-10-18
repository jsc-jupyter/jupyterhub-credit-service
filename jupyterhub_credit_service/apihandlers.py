import asyncio
import sys

if sys.version_info >= (3, 10):
    from contextlib import aclosing
else:
    from async_generator import aclosing

from jupyterhub.apihandlers.base import APIHandler
from jupyterhub.scopes import needs_scope
from jupyterhub.utils import iterate_until
from tornado import web
from tornado.iostream import StreamClosedError
from tornado.web import HTTPError, authenticated

from .orm import ProjectCredits, UserCredits

background_task = None
import json


def get_model(user_credits):
    model = {
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
    return model


class CreditsSSEAPIHandler(APIHandler):
    """EventStream handler to update UserCredits in Frontend"""

    keepalive_interval = 8
    keepalive_task = None

    def get_content_type(self):
        return "text/event-stream"

    async def send_event(self, event):
        try:
            self.write(f"data: {json.dumps(event)}\n\n")
            await self.flush()
        except StreamClosedError:
            # raise Finish to halt the handler
            raise web.Finish()

    def initialize(self):
        super().initialize()
        self._finish_future = asyncio.Future()

    def on_finish(self):
        self._finish_future.set_result(None)
        self.keepalive_task = None

    async def keepalive(self):
        """Write empty lines periodically

        to avoid being closed by intermediate proxies
        when there's a large gap between events.
        """
        while not self._finish_future.done():
            try:
                self.write("\n\n")
                await self.flush()
            except (StreamClosedError, RuntimeError):
                return

            await asyncio.wait([self._finish_future], timeout=self.keepalive_interval)

    async def get_user_credits(self, user):
        user_credits = UserCredits.get_user(user.authenticator.db_session, user.name)
        model = get_model(user_credits)
        return model

    async def event_handler(self, user):
        sse_event = user.authenticator.user_credits_sse_event

        while (
            type(self._finish_future) is asyncio.Future
            and not self._finish_future.done()
        ):
            model_credits = await self.get_user_credits(user)
            try:
                yield model_credits
            except GeneratorExit as e:
                raise e
            finally:
                sse_event.clear()
            await sse_event.wait()

    @authenticated
    async def get(self):
        self.set_header("Cache-Control", "no-cache")
        user = await self.get_current_user()

        # start sending keepalive to avoid proxies closing the connection
        # This task will be finished / done, once the tab in the browser is closed
        self.keepalive_task = asyncio.create_task(self.keepalive())

        try:
            async with aclosing(
                iterate_until(self.keepalive_task, self.event_handler(user))
            ) as events:
                async for event in events:
                    if event:
                        await self.send_event(event)
                    else:
                        break
        except RuntimeError:
            pass
        except asyncio.exceptions.CancelledError:
            pass


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

        model = get_model(user_credits)

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
