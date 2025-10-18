import inspect
import os

from jupyterhub.spawner import Spawner
from tornado import web
from traitlets import Any

from .orm import UserCredits as ORMUserCredits


class CreditsException(web.HTTPError):
    jupyterhub_html_message = None

    def __init__(self, log_msg):
        super().__init__(403, log_msg)
        self.jupyterhub_html_message = log_msg


class CreditsSpawner(Spawner):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.user.authenticator.credits_append_user(self.user)

    _billing_interval = None
    billing_interval = Any(
        default_value=int(os.environ.get("JUPYTERHUB_CREDITS_BILLING_INTERVAL", "600")),
        help="""
        Interval, in seconds, at which user credits will be billed while a
        single-user notebook server is running.

        Every `billing_interval` seconds, the user's credits will be reduced by
        the configured `billing_value`.

        This can be:
        - An integer value
        - A function returning an integer
        - A coroutine returning an integer

        This allows you to define dynamic billing intervals based on spawner state,
        user options, or other runtime conditions.

        This may be a coroutine.

        Example::

            def get_billing_interval(spawner):
                if spawner.user_options.get("slowcheck"):
                    return 1200
                return 600

            c.CreditsSpawner.billing_interval = get_billing_interval

        The default is 600 seconds.
        """,
    ).tag(config=True)

    # We use _billing_value to be used in user.authenticator.
    # It is also stored in the spawner.state in database.
    # This way it's still available after a hub-restart.
    _billing_value = None
    billing_value = Any(
        default_value=int(os.environ.get("JUPYTERHUB_CREDITS_BILLING_VALUE", "10")),
        help="""
        Number of credits deducted from a user account every `billing_interval`
        seconds while their single-user notebook server is running.

        If a user runs out of credits, their server will be stopped.

        This can be:
        - An integer value
        - A function returning an integer
        - A coroutine returning an integer

        This allows for flexible billing policies, such as different rates based on
        user options or resource profiles.

        This may be a coroutine.

        Example::

            def get_billing_value(spawner):
                values = {
                    "normal": 5,
                    "power": 10,
                }
                mode = spawner.user_options.get("mode", [None])[0]
                return values.get(mode, 5)

            c.CreditsSpawner.billing_value = get_billing_value

        The default is 10 credits per interval.
        """,
    ).tag(config=True)

    def load_state(self, state):
        super().load_state(state)
        if "billing_value" in state:
            self._billing_value = state["billing_value"]
        if "billing_interval" in state:
            self._billing_interval = state["billing_interval"]

    def get_state(self):
        state = super().get_state()
        if self._billing_value:
            state["billing_value"] = self._billing_value
        if self._billing_interval:
            state["billing_interval"] = self._billing_interval
        return state

    def clear_state(self):
        super().clear_state()

    async def progress(self):
        yield {
            "progress": 50,
            "message": f"Spawning server for {self._billing_value} credits per {self._billing_interval} seconds...",
        }

    async def run_pre_spawn_hook(self):
        if self.user.authenticator.credits_enabled:
            await self.user.authenticator.update_user_credit(self.user.orm_user)

            async def resolve_value(value):
                if callable(value):
                    value = value(self)
                if inspect.isawaitable(value):
                    value = await value
                return value

            self._billing_interval = await resolve_value(self.billing_interval)
            self._billing_value = await resolve_value(self.billing_value)

            user_credits = ORMUserCredits.get_user(
                self.user.authenticator.db_session, self.user.name
            )
            if not user_credits:
                raise CreditsException(
                    "No credit values available. Please re-login and try again."
                )
            available_balance = 0
            proj_credits = user_credits.project
            if proj_credits:
                available_balance += proj_credits.balance
            available_balance += user_credits.balance

            if available_balance < self._billing_value:
                error_proj_msg = ""
                error_proj_msg_2 = ""
                if proj_credits:
                    error_proj_msg = f"<br>Current project ({proj_credits.name}) credits: {proj_credits.balance} / {proj_credits.cap}."
                    error_proj_msg_2 = f"<br>Your project ({proj_credits.name}) will receive {proj_credits.grant_value} credits every {proj_credits.grant_interval} seconds."
                raise CreditsException(
                    f"Not enough credits to start server '{self._log_name}'.<br>Required credits: {self._billing_value}.<br>Current User credits: {user_credits.balance} / {user_credits.cap}.{error_proj_msg}<br>You will receive {user_credits.grant_value} credits every {user_credits.grant_interval} seconds.{error_proj_msg_2}"
                )

        return super().run_pre_spawn_hook()

    async def start(self):
        _start = super().start()
        if inspect.isawaitable(_start):
            _start = await _start
        return _start

    async def poll(self):
        _poll = super().poll()
        if inspect.isawaitable(_poll):
            _poll = await _poll
        return _poll

    async def stop(self):
        _stop = super().stop()
        if inspect.isawaitable(_stop):
            _stop = await _stop
        return _stop
