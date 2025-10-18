import asyncio
import inspect
import os
import time
from datetime import datetime, timedelta

from jupyterhub import orm
from jupyterhub.auth import Authenticator
from jupyterhub.orm import User as ORMUser
from jupyterhub.utils import utcnow
from traitlets import Any, Bool, Callable, Dict, Integer, List, Union

from .orm import Base
from .orm import ProjectCredits as ORMProjectCredits
from .orm import UserCredits as ORMUserCredits


class CreditsAuthenticator(Authenticator):
    credits_task = None
    db_session = None
    user_credits_dict = {}
    user_credits_sse_event = asyncio.Event()

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

    credits_user_project = Callable(
        default_value=None,
        allow_none=True,
        help="""
        Callable to define a name of a project a user
        is part of. The project must be configured via
        `c.CreditsAuthenticator.credits_available_projects`.

        This may be a coroutine.

        Example::

            def credits_user_project(user_name, user_groups, is_admin):
                if "community1" in user_groups:
                    return "community1"
                return None

            c.CreditsAuthenticator.credits_user_project = credits_user_project
        
        Default: None
        """,
    ).tag(config=True)

    credits_available_projects = Union(
        [List(Dict()), Callable()],
        default_value=[],
        help="""
        Define a list of available projects a user can be part of. 
        The required structure for one project is:
            {
                "name": "my_project",
                "cap": 500,
                "grant_value": 10,
                "grant_interval": 300
            }

        For a user to join a project configure credits_user_project.
        Each user can only join maximum one project.

        If the user is part of a project, the project's credits take precedence.
        This means that as long as the project has available credits, they will be
        used first. The user's personal credits are only used if the project
        has no credits left.

        If it is configured as a Callable, it will be updated at every user login.
        This allows you to use an external source and manage projects without restarting
        JupyterHub.

        May be a coroutine.

        Example::

            async def available_projects():
                return [{
                    "name": "community1",
                    "cap": 1000,
                    "grant_value": 20,
                    "grant_interval": 600,
                },
                {
                    "name": "community2",
                    "cap": 500,
                    "grant_value": 10,
                    "grant_interval": 600,
                }]

            c.CreditsAuthenticator.credits_available_projects = available_projects

        Default: []
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

    async def credit_reconciliation_task(self):
        while True:
            try:
                tic = time.time()
                now = utcnow(with_tz=False)
                all_user_credits = self.db_session.query(ORMUserCredits).all()

                for credits in all_user_credits:
                    try:
                        available_balance = 0

                        if credits.project:
                            proj_prev_balance = credits.project.balance
                            proj_cap = credits.project.cap
                            proj_updated = False
                            if proj_prev_balance == proj_cap:
                                credits.project.grant_last_update = now
                                proj_updated = True
                            elif proj_prev_balance > proj_cap:
                                credits.project.grant_last_update = now
                                credits.project.balance = proj_cap
                                proj_updated = True
                            else:
                                elapsed = (
                                    now - credits.project.grant_last_update
                                ).total_seconds()
                                if elapsed > credits.project.grant_interval:
                                    proj_updated = True
                                    grants = int(
                                        elapsed // credits.project.grant_interval
                                    )
                                    gained = grants * credits.project.grant_value
                                    credits.project.balance = min(
                                        proj_prev_balance + gained, proj_cap
                                    )
                                    credits.project.grant_last_update += timedelta(
                                        seconds=grants * credits.project.grant_interval
                                    )
                                    self.log.debug(
                                        f"Project {credits.project_name}: {proj_prev_balance} -> {credits.project.balance} "
                                        f"(+{gained}, cap {credits.project.cap})",
                                        extra={
                                            "action": "creditsgained",
                                            "projectname": credits.project_name,
                                        },
                                    )
                            if proj_updated:
                                self.db_session.commit()
                            available_balance += credits.project.balance
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
                        available_balance += credits.balance

                        mem_user = self.user_credits_dict.get(credits.name, None)
                        if mem_user:
                            to_stop = []
                            for spawner in mem_user.spawners.values():
                                if not getattr(spawner, "_billing_interval", None):
                                    continue
                                if not getattr(spawner, "_billing_value", None):
                                    continue
                                try:
                                    spawner_id_str = str(spawner.orm_spawner.id)
                                    if not spawner.active:
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
                                        if cost > available_balance:
                                            # Stop Server. Not enough credits left for next interval
                                            to_stop.append(spawner.name)
                                            self.log.info(
                                                f"User Credits exceeded. Stopping Server '{mem_user.name}:{spawner.name}' (Credits available: {available_balance}, Cost: {cost})",
                                                extra={
                                                    "action": "creditsexceeded",
                                                    "userid": mem_user.id,
                                                    "username": mem_user.name,
                                                    "servername": spawner.name,
                                                },
                                            )
                                        else:
                                            if credits.project:
                                                if cost > credits.project.balance:
                                                    proj_cost = credits.project.balance
                                                else:
                                                    proj_cost = cost
                                                credits.project.balance -= proj_cost
                                                cost -= proj_cost
                                                self.log.debug(
                                                    f"Project {credits.project_name} credits recuded by {proj_cost} ({proj_prev_balance} -> {credits.project.balance}) for server '{spawner._log_name}' ({elapsed}s since last bill timestamp)",
                                                    extra={
                                                        "action": "creditspaid",
                                                        "userid": mem_user.id,
                                                        "username": mem_user.name,
                                                        "servername": spawner.name,
                                                        "projectname": credits.project_name,
                                                    },
                                                )

                                            credits.balance -= cost
                                            if not force_bill:
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
                self.user_credits_sse_event.set()
                tac = time.time() - tic
                self.log.debug(f"Credit task took {tac}s to update all user credits")
                await asyncio.sleep(self.credits_task_interval)

    def credits_append_user(self, user):
        if user.name not in self.user_credits_dict.keys():
            self.user_credits_dict[user.name] = user

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
            self.credits_task = asyncio.create_task(self.credit_reconciliation_task())

    async def update_user_credit(self, orm_user):
        # Create new ORMUserCredits or ORMProjectCredits entries
        # or Update existing ones, if the config returns new values
        # than listed in the db
        async def resolve_value(value):
            if callable(value):
                value = value(orm_user.name, orm_user.groups, orm_user.admin)
            if inspect.isawaitable(value):
                value = await value
            return value

        # Check if all configured projects are in database
        available_projects = self.credits_available_projects
        if callable(available_projects):
            available_projects = available_projects()
            if inspect.isawaitable(available_projects):
                available_projects = await available_projects

        for project in available_projects:
            if not project.get("name", None):
                self.log.warning(
                    "Credits Project requires a 'name'. Fix required for Authenticator.credits_available_projects. Skip project"
                )
                continue
            project_name = project["name"]
            if "cap" not in project.keys():
                self.log.warning(
                    f"Credits Project requires a 'cap'. Fix required for Authenticator.credits_available_projects. Skip project {project_name}"
                )
                continue
            if "grant_value" not in project.keys():
                self.log.warning(
                    f"Credits Project requires a 'grant_value'. Fix required for Authenticator.credits_available_projects. Skip project {project_name}"
                )
                continue
            if "grant_interval" not in project.keys():
                self.log.warning(
                    f"Credits Project requires a 'grant_interval'. Fix required for Authenticator.credits_available_projects. Skip project {project_name}"
                )
                continue

            orm_project_credits = ORMProjectCredits.get_project(
                self.db_session, project_name=project_name
            )
            if not orm_project_credits:
                # Create entry in database
                project["balance"] = project["cap"]
                orm_project_credits = ORMProjectCredits(**project)
                self.db_session.add(orm_project_credits)
                self.db_session.commit()
            else:
                # Check + Update project
                prev_project_balance = orm_project_credits.balance
                prev_project_cap = orm_project_credits.cap
                prev_project_grant_value = orm_project_credits.grant_value
                prev_project_grant_interval = orm_project_credits.grant_interval
                proj_updated = False
                if prev_project_cap != project["cap"]:
                    proj_updated = True
                    orm_project_credits.cap = project["cap"]
                    if prev_project_balance > orm_project_credits.cap:
                        orm_project_credits.balance = orm_project_credits.cap
                if prev_project_grant_value != project["grant_value"]:
                    proj_updated = True
                    orm_project_credits.grant_value = project["grant_value"]
                if prev_project_grant_interval != project["grant_interval"]:
                    proj_updated = True
                    orm_project_credits.grant_interval = project["grant_interval"]
                if proj_updated:
                    self.db_session.commit()

        cap = await resolve_value(self.credits_user_cap)
        user_grant_value = await resolve_value(self.credits_user_grant_value)
        user_grant_interval = await resolve_value(self.credits_user_grant_interval)
        user_project_name = await resolve_value(self.credits_user_project)

        credits_values = {
            "cap": cap,
            "grant_value": user_grant_value,
            "grant_interval": user_grant_interval,
            "grant_last_update": utcnow(with_tz=False),
            "project": None,
        }
        if user_project_name:
            orm_user_project = ORMProjectCredits.get_project(
                self.db_session, user_project_name
            )
            if orm_user_project:
                credits_values["project"] = orm_user_project
            else:
                self.log.warning(
                    f"Configured project ({user_project_name}) for {orm_user.name} not in Authenticator.available_projects"
                )

        # Add / Update ORMUserCredits entry
        orm_user_credits = ORMUserCredits.get_user(self.db_session, orm_user.name)

        if not orm_user_credits:
            credits_values["balance"] = credits_values["cap"]
            orm_user_credits = ORMUserCredits(name=orm_user.name, **credits_values)
            self.db_session.add(orm_user_credits)
            self.db_session.commit()
        else:
            prev_user_balance = orm_user_credits.balance
            prev_user_cap = orm_user_credits.cap
            prev_grant_value = orm_user_credits.grant_value
            prev_grant_interval = orm_user_credits.grant_interval
            prev_project = orm_user_credits.project
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
            if getattr(prev_project, "name", None) != credits_values["project"]:
                updated = True
                orm_user_credits.project = credits_values["project"]
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
