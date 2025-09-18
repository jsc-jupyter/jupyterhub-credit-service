import asyncio
import inspect
import os
import time
from datetime import datetime, timedelta

from jupyterhub import orm
from jupyterhub.auth import Authenticator
from jupyterhub.orm import User as ORMUser
from jupyterhub.utils import utcnow
from traitlets import Any, Bool, Integer

from .orm import Base
from .orm import UserCredits as ORMUserCredits


class CreditsAuthenticator(Authenticator):
    credits_task = None
    db_session = None
    user_dict = {}

    credits_enabled = Bool(
        default_value=os.environ.get("JUPYTERHUB_CREDITS_ENABLED", "1").lower()
        in ["1", "true"],
        help="""
        Enable or disable the credits feature.

        If disabled, no credits will be deducted or granted to users,
        and servers will not be stopped due to lack of credits.

        Default: enabled.
        """,
    ).tag(config=True)

    credits_task_interval = Integer(
        default_value=int(os.environ.get("JUPYTERHUB_CREDITS_TASK_INTERVAL", "60")),
        help="""
        Interval, in seconds, at which the background credit task runs.

        This task is responsible for billing running servers and granting
        credits to users periodically.

        Default: 60 seconds.
        """,
    ).tag(config=True)

    credits_user_cap = Any(
        default_value=int(os.environ.get("JUPYTERHUB_CREDITS_USER_CAP", "100")),
        help="""
        Maximum credit balance for all users.

        This value can be:
        - An integer (applies to all users)
        - A function returning an integer (per-user logic)
        - A coroutine returning an integer (per-user logic)

        This may be a coroutine.

        Example::

            def user_cap(user_name, user_groups, is_admin):
                if user_name == "max":
                    return 150
                return 100

            c.CreditsAuthenticator.credits_user_cap = user_cap
        
        Default: 100 credits
        """,
    ).tag(config=True)

    credits_user_grant_value = Any(
        default_value=int(os.environ.get("JUPYTERHUB_CREDITS_USER_GRANT_VALUE", "10")),
        help="""
        Number of credits granted to a user every
        `c.CreditsAuthenticator.user_grant_interval` seconds.

        This value can be:
        - An integer (applies to all users)
        - A function returning an integer (per-user logic)
        - A coroutine returning an integer (per-user logic)

        This may be a coroutine.

        Example::

            def user_grant_value(user_name, user_groups, is_admin):
                if is_admin:
                    return 20
                return 10

            c.CreditsAuthenticator.credits_user_grant_value = user_grant_value
        
        Default: 10 credits
        """,
    ).tag(config=True)

    credits_user_grant_interval = Any(
        default_value=int(
            os.environ.get("JUPYTERHUB_CREDITS_USER_GRANT_INTERVAL", "600")
        ),
        help="""
        Interval, in seconds, for granting
        `c.CreditsAuthenticator.user_grant_value` credits to users.

        This value can be:
        - An integer (applies to all users)
        - A function returning an integer (per-user logic)
        - A coroutine returning an integer (per-user logic)

        This may be a coroutine.

        Example::

            def user_grant_interval(user_name, user_groups, is_admin):
                if "premium" in user_groups:
                    return 300  # grant every 5 minute
                return 600  # default 10 minutes

            c.CreditsAuthenticator.credits_user_grant_interval = user_grant_interval
        
        Default: 600 seconds
        """,
    ).tag(config=True)

    credits_task_post_hook = Any(
        default_value=None,
        help="""
        An optional hook function that is run after each credit task execution.

        This can be used to implement logging, metrics collection,
        or custom actions after credits are billed and granted.

        This may be a coroutine.

        Example::

            async def my_task_hook(credits_manager):
                print("Credits task finished")

            c.CreditsAuthenticator.credits_task_post_hook = my_task_hook
        """,
    ).tag(config=True)

    async def run_credits_task_post_hook(self):
        if self.credits_task_post_hook:
            f = self.credits_task_post_hook()
            if inspect.isawaitable(f):
                await f

    async def credit_reconciliation_task(self, interval):
        while True:
            try:
                tic = time.time()
                now = utcnow(with_tz=False)
                all_user_credits = self.db_session.query(ORMUserCredits).all()

                for credits in all_user_credits:
                    try:
                        prev_balance = credits.balance
                        cap = credits.cap
                        updated = False
                        if prev_balance == cap:
                            credits.grant_last_update = now
                            updated = True
                        elif prev_balance > cap:
                            credits.grant_last_update = now
                            credits.balance = cap
                            updated = True
                        else:
                            elapsed = (now - credits.grant_last_update).total_seconds()
                            if elapsed >= credits.grant_interval:
                                updated = True
                                grants = int(elapsed // credits.grant_interval)
                                gained = grants * credits.grant_value
                                credits.balance = min(prev_balance + gained, cap)
                                credits.grant_last_update += timedelta(
                                    seconds=grants * credits.grant_interval
                                )
                                self.log.debug(
                                    f"User {credits.name}: {prev_balance} -> {credits.balance} "
                                    f"(+{gained}, cap {credits.cap})",
                                    extra={
                                        "action": "creditsgained",
                                        "username": credits.name,
                                    },
                                )
                        if updated:
                            self.db_session.commit()
                        mem_user = self.user_dict.get(credits.name, None)
                        if mem_user:
                            to_stop = []
                            for spawner in mem_user.spawners.values():
                                try:
                                    spawner_id_str = str(spawner.orm_spawner.id)
                                    if spawner.server is None:
                                        if (
                                            spawner_id_str
                                            in credits.spawner_bills.keys()
                                        ):
                                            del credits.spawner_bills[spawner_id_str]
                                        continue
                                    if not spawner.ready:
                                        continue
                                    last_billed = None
                                    # When restarting the Hub the last bill timestamp
                                    # will be stored in the database. Use this one.
                                    force_bill = False
                                    if spawner_id_str in credits.spawner_bills.keys():
                                        last_billed = datetime.fromisoformat(
                                            credits.spawner_bills[spawner_id_str]
                                        )
                                        # If the last bill timestamp is older than started, it's from
                                        # a previous running lab and should not be used.
                                        if last_billed < spawner.orm_spawner.started:
                                            force_bill = True
                                            last_billed = now
                                    else:
                                        # If no bill timestamp is available we'll use the current timestamp
                                        # Using started would be unfair, since we don't know how long it took
                                        # to actually be usable. Users should only "pay" for ready spawners.
                                        force_bill = True
                                        last_billed = now

                                    elapsed = (now - last_billed).total_seconds()
                                    if (
                                        elapsed >= spawner._billing_interval
                                        or force_bill
                                    ):
                                        # When force_bill is true we have to make sure to bill the first
                                        # interval as well
                                        bills = max(
                                            int(elapsed // spawner._billing_interval), 1
                                        )
                                        cost = bills * spawner._billing_value
                                        prev_balance = credits.balance
                                        if cost > prev_balance:
                                            # Stop Server. Not enough credits left for next interval
                                            to_stop.append(spawner.name)
                                            self.log.info(
                                                f"User Credits exceeded. Stopping Server '{mem_user.name}:{spawner.name}' (Credits left: {prev_balance}, Cost: {cost})",
                                                extra={
                                                    "action": "creditsexceeded",
                                                    "userid": mem_user.id,
                                                    "username": mem_user.name,
                                                    "servername": spawner.name,
                                                },
                                            )
                                        else:
                                            credits.balance -= cost
                                            last_billed += timedelta(
                                                seconds=bills
                                                * spawner._billing_interval
                                            )
                                            self.log.debug(
                                                f"User {mem_user.name} credits recuded by {cost} ({prev_balance} -> {credits.balance}) for server '{spawner._log_name}' ({elapsed}s since last bill timestamp)",
                                                extra={
                                                    "action": "creditspaid",
                                                    "userid": mem_user.id,
                                                    "username": mem_user.name,
                                                    "servername": spawner.name,
                                                },
                                            )
                                            credits.spawner_bills[spawner_id_str] = (
                                                last_billed.isoformat()
                                            )
                                            self.db_session.commit()
                                except:
                                    self.log.exception(
                                        f"Error while updating user credits for {credits} in spawner {spawner._log_name}."
                                    )

                            for spawner_name in to_stop:
                                asyncio.create_task(mem_user.stop(spawner_name))
                    except:
                        self.log.exception(
                            f"Error while updating user credits for {credits}."
                        )
            except:
                self.log.exception("Error while updating user credits.")
            finally:
                try:
                    await self.run_credits_task_post_hook()
                except:
                    self.log.exception("Exception in credits_task_post_hook")
                tac = time.time() - tic
                self.log.debug(f"Credit task took {tac}s to update all user credits")
                await asyncio.sleep(interval)

    def append_user(self, user):
        if user.name not in self.user_dict.keys():
            self.user_dict[user.name] = user

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.credits_enabled:
            hub = self.parent
            session_factory = orm.new_session_factory(
                hub.db_url, reset=hub.reset_db, echo=hub.debug_db, **hub.db_kwargs
            )
            self.db_session = session_factory()
            from sqlalchemy import create_engine

            engine = create_engine(hub.db_url)
            Base.metadata.create_all(engine)
            self.credits_task = asyncio.create_task(
                self.credit_reconciliation_task(self.credits_task_interval)
            )

    async def update_user_credit(self, orm_user):
        async def resolve_value(value):
            if callable(value):
                value = value(orm_user.name, orm_user.groups, orm_user.admin)
            if inspect.isawaitable(value):
                value = await value
            return value

        cap = await resolve_value(self.credits_user_cap)
        user_grant_value = await resolve_value(self.credits_user_grant_value)
        user_grant_interval = await resolve_value(self.credits_user_grant_interval)

        credits_values = {
            "cap": cap,
            "grant_value": user_grant_value,
            "grant_interval": user_grant_interval,
            "grant_last_update": utcnow(with_tz=False),
        }

        orm_user_credits = ORMUserCredits.get_user(self.db_session, orm_user.name)

        if not orm_user_credits:
            credits_values["balance"] = credits_values["cap"]
            user_credits = ORMUserCredits(name=orm_user.name, **credits_values)
            self.db_session.add(user_credits)
            self.db_session.commit()
        else:
            prev_user_balance = orm_user_credits.balance
            prev_user_cap = orm_user_credits.cap
            prev_grant_value = orm_user_credits.grant_value
            prev_grant_interval = orm_user_credits.grant_interval
            updated = False
            if prev_user_cap != credits_values["cap"]:
                updated = True
                orm_user_credits.cap = credits_values["cap"]
                if prev_user_balance > orm_user_credits.cap:
                    orm_user_credits.balance = orm_user_credits.cap
            if prev_grant_value != credits_values["grant_value"]:
                updated = True
                orm_user_credits.grant_value = credits_values["grant_value"]
            if prev_grant_interval != credits_values["grant_interval"]:
                updated = True
                orm_user_credits.grant_interval = credits_values["grant_interval"]
            if updated:
                self.db_session.commit()

    async def run_post_auth_hook(self, handler, auth_model):
        if self.credits_enabled:
            orm_user = (
                self.db_session.query(ORMUser)
                .filter(ORMUser.name == auth_model["name"])
                .first()
            )
            # If it's a new user there won't be an entry.
            # This case will be handled in .add_user()
            if orm_user:
                await self.update_user_credit(orm_user)
        return await super().run_post_auth_hook(handler, auth_model)

    async def add_user(self, orm_user):
        super().add_user(orm_user)
        if self.credits_enabled:
            await self.update_user_credit(orm_user)
