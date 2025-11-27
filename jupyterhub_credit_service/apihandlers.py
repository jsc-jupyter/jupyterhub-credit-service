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

from .orm import CreditsProject, CreditsUser

background_task = None
import json


def get_model(credits_user):
    model = []
    for cuv in credits_user.credits_user_values:
        model.append(
            {
                "name": cuv.name,
                "balance": cuv.balance,
                "cap": cuv.cap,
                "grant_value": cuv.grant_value,
                "grant_interval": cuv.grant_interval,
                "grant_last_update": cuv.grant_last_update.isoformat(),
            }
        )
        if cuv.project:
            model[-1].update(
                {
                    "project": {
                        "name": cuv.project.name,
                        "balance": cuv.project.balance,
                        "cap": cuv.project.cap,
                        "grant_value": cuv.project.grant_value,
                        "grant_interval": cuv.project.grant_interval,
                        "grant_last_update": cuv.project.grant_last_update.isoformat(),
                    }
                }
            )
    return model


class CreditsSSEAPIHandler(APIHandler):
    """EventStream handler to update UserCredits in Frontend"""

    def check_xsrf_cookie(self):
        pass

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

    async def event_handler(self, user):
        user_credits = CreditsUser.get_user(user.authenticator.parent.db, user.name)

        while (
            type(self._finish_future) is asyncio.Future
            and not self._finish_future.done()
        ):
            user.authenticator.parent.db.refresh(user_credits)
            model_credits = get_model(user_credits)
            try:
                yield model_credits
            except GeneratorExit as e:
                raise e
            await user.authenticator.credits_task_event.wait()
            await asyncio.sleep(0)

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


class CreditsSSEServerAPIHandler(CreditsSSEAPIHandler):
    """EventStream handler to update UserCredits in Frontend for one specific server"""

    async def event_handler(self, user, spawner):
        user_options = spawner.user_options
        user_credits = CreditsUser.get_user(user.authenticator.parent.db, user.name)
        credits_user_values = None
        default_cuv = None
        for cuv in user_credits.credits_user_values:
            if not cuv.user_options:
                default_cuv = cuv
                continue
            match = user.authenticator.match_user_options(
                user_options, cuv.user_options or {}
            )
            if match:
                credits_user_values = cuv
                break
        if credits_user_values is None:
            credits_user_values = default_cuv
        while (
            type(self._finish_future) is asyncio.Future
            and not self._finish_future.done()
        ):
            if not spawner.ready:
                try:
                    yield {
                        "error": "Your Server is no longer running.\nRestart of Jupyter Server required."
                    }
                    return
                except GeneratorExit as e:
                    raise e
            elif credits_user_values:
                user.authenticator.parent.db.refresh(credits_user_values)
                model_credits = {
                    "balance": credits_user_values.balance,
                    "cap": credits_user_values.cap,
                }
                if credits_user_values.project:
                    user.authenticator.parent.db.refresh(credits_user_values.project)
                    model_credits["project"] = {
                        "name": credits_user_values.project.name,
                        "balance": credits_user_values.project.balance,
                        "cap": credits_user_values.project.cap,
                    }
                try:
                    yield model_credits
                except GeneratorExit as e:
                    raise e
            await user.authenticator.credits_task_event.wait()
            await asyncio.sleep(0)

    @needs_scope("read:servers")
    async def get(self, user_name, server_name=None):
        self.set_header("Cache-Control", "no-cache")
        if server_name is None:
            server_name = ""
        user = self.find_user(user_name)
        if user is None:
            # no such user
            raise web.HTTPError(404)
        if server_name not in user.spawners:
            # user has no such server
            raise web.HTTPError(404)
        spawner = user.spawners[server_name]
        if not spawner.ready:
            raise web.HTTPError(409, "Server is not running.")

        # start sending keepalive to avoid proxies closing the connection
        # This task will be finished / done, once the tab in the browser is closed
        self.keepalive_task = asyncio.create_task(self.keepalive())

        try:
            async with aclosing(
                iterate_until(self.keepalive_task, self.event_handler(user, spawner))
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


from jupyterhub.apihandlers.users import UserServerAPIHandler


class CreditsStopServerAPIHandler(UserServerAPIHandler):
    @needs_scope("access:servers")
    async def delete(self, user_name, server_name=""):
        user = self.find_user(user_name)

        if server_name:
            if server_name not in user.orm_spawners:
                raise web.HTTPError(
                    404, f"{user_name} has no server named '{server_name}'"
                )
        spawner = user.spawners[server_name]
        self.log.info(
            f"{spawner._log_name} - Stopping server '{server_name}' for user '{user_name}' per API request due to JupyterLab Credits topbar extension."
        )
        if spawner.pending == "stop":
            self.log.debug("%s already stopping", spawner._log_name)
            self.set_header("Content-Type", "text/plain")
            self.set_status(202)
            return

        # stop_future = None
        if spawner.pending:
            # we are interrupting a pending start
            # hopefully nothing gets leftover
            self.log.warning(
                f"Interrupting spawner {spawner._log_name}, pending {spawner.pending}"
            )
            spawn_future = spawner._spawn_future
            if spawn_future:
                spawn_future.cancel()
            # Give cancel a chance to resolve?
            # not sure what we would wait for here,
            # await asyncio.sleep(1)
            asyncio.create_task(self.stop_single_user(user, server_name))

        elif spawner.ready:
            # include notify, so that a server that died is noticed immediately
            status = await spawner.poll_and_notify()
            if status is None:
                asyncio.create_task(self.stop_single_user(user, server_name))

        status = 202 if spawner._stop_pending else 204
        self.set_header("Content-Type", "text/plain")
        self.set_status(status)


class CreditsAPIHealthHandler(APIHandler):
    @authenticated
    async def get(self):
        self.write(json.dumps({"status": "ok"}))


class CreditsAPIHandler(APIHandler):
    @authenticated
    async def get(self):
        user = await self.get_current_user()
        if not user:
            raise HTTPError(403, "Not authenticated")

        if not user.authenticator.credits_enabled:
            raise HTTPError(404, "Credits function is currently disabled")

        credits_user = CreditsUser.get_user(user.authenticator.parent.db, user.name)

        if not credits_user:
            # Create entry for user with default values
            raise HTTPError(404, "No credit entry found for user")

        model = get_model(credits_user)

        self.write(json.dumps(model))


class CreditsUserAPIHandler(APIHandler):
    @needs_scope("admin:users")
    async def post(self, user_name, credit_name):
        user = self.find_user(user_name)
        if not user:
            raise HTTPError(404, "User not found")
        data = self.get_json_body()
        credits_user = CreditsUser.get_user(user.authenticator.parent.db, user.name)
        if not credits_user:
            # Create entry for user with default values
            raise HTTPError(404, "No credit entry found for user")
        balance = cap = grant_value = grant_interval = None
        project_balance = project_cap = project_grant_value = project_grant_interval = (
            None
        )
        credits_user_values = None
        for cuv in credits_user.credits_user_values:
            if cuv.name == credit_name:
                credits_user_values = cuv
                balance = data.get("balance", None)
                cap = data.get("cap", None)
                grant_value = data.get("grant_value", None)
                grant_interval = data.get("grant_interval", None)
                project = data.get("project", None)
                if project:
                    project_balance = project.get("balance", None)
                    project_cap = project.get("cap", None)
                    project_grant_value = project.get("grant_value", None)
                    project_grant_interval = project.get("grant_interval", None)
                break
        if not credits_user_values:
            raise HTTPError(404, f"Credit entry '{credit_name}' not found for user")
        if balance and cap and balance > cap:
            raise HTTPError(
                400, f"Balance can't be bigger than cap ({balance} / {cap})"
            )
        if balance and balance > credits_user_values.cap:
            raise HTTPError(
                400,
                f"Balance can't be bigger than cap ({balance} / {credits_user_values.cap})",
            )
        if balance and balance < 0:
            raise HTTPError(400, "Balance can't be negative")
        if balance:
            credits_user_values.balance = balance
        if cap:
            credits_user_values.cap = cap
        if grant_value:
            credits_user_values.grant_value = grant_value
        if grant_interval:
            credits_user_values.grant_interval = grant_interval
        if project and credits_user_values.project:
            prev_project_balance = credits_user_values.project.balance
            prev_project_cap = credits_user_values.project.cap
            prev_project_grant_value = credits_user_values.project.grant_value
            prev_project_grant_interval = credits_user_values.project.grant_interval
            proj_updated = False
            if project_cap and prev_project_cap != project_cap:
                proj_updated = True
                credits_user_values.project.cap = project_cap
            if project_balance and prev_project_balance != project_balance:
                proj_updated = True
                credits_user_values.project.balance = project_balance
            if credits_user_values.project.cap < credits_user_values.project.balance:
                credits_user_values.project.balance = credits_user_values.project.cap
            if project_grant_value and prev_project_grant_value != project_grant_value:
                proj_updated = True
                credits_user_values.project.grant_value = project_grant_value
            if (
                project_grant_interval
                and prev_project_grant_interval != project_grant_interval
            ):
                proj_updated = True
                credits_user_values.project.grant_interval = project_grant_interval
            if proj_updated:
                user.authenticator.parent.db.add(credits_user_values.project)
                user.authenticator.parent.db.commit()
        elif project and not credits_user_values.project:
            _project = user.authenticator.credits_validate_and_update_project(
                credits_user_values
            )
            if not _project:
                self.log.error(
                    f"Failed to validate and update project: {credits_user_values}"
                )
                self.set_status(400)
                return
            else:
                _project["balance"] = _project["cap"]
                orm_project = CreditsProject(**_project)
                user.authenticator.parent.db.add(orm_project)
                credits_user_values.project = orm_project
                user.authenticator.parent.db.commit()
        elif not project and credits_user_values.project:
            user.authenticator.parent.db.delete(credits_user_values.project)
            credits_user_values.project = None

        user.authenticator.parent.db.add(credits_user)
        user.authenticator.parent.db.commit()
        self.set_status(200)


class CreditsProjectAPIHandler(APIHandler):
    @needs_scope("admin:users")
    async def post(self, project_name):
        data = self.get_json_body()
        balance = data.get("balance", None)
        cap = data.get("cap", None)
        grant_value = data.get("grant_value", None)
        grant_interval = data.get("grant_interval", None)

        project = CreditsProject.get_project(
            self.current_user.authenticator.parent.db, project_name
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
        self.current_user.authenticator.parent.db.commit()
        self.set_status(200)
