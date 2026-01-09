import asyncio
import fnmatch
import inspect
import os
import re
import time
from datetime import datetime, timedelta

from jupyterhub.auth import Authenticator
from jupyterhub.orm import User as ORMUser
from jupyterhub.utils import utcnow
from sqlalchemy import inspect as sqlinspect
from traitlets import Any, Bool, Callable, Dict, Integer, List, Union

from .orm import Base, CreditsProject, CreditsUser, CreditsUserValues


class CreditsAuthenticator(Authenticator):
    credits_task = None
    user_credits_dict = {}
    credits_task_event = None

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

    credits_user = Union(
        [Dict(), List(), Callable()],
        default_value=None,
        help="""
        Configuration dictionaries for user credits.
        
        Each configuration must include the following keys:
        - name: A unique identifier. Required to remove previously granted credit configurations from a user.
        - cap: Maximum credit balance for the user. (Has to be an Integer)
        - grant_value: Number of credits granted to the user every grant_interval seconds. (Has to be an Integer)
        - grant_interval: Interval, in seconds, for granting credits to the user. (Has to be an Integer)
        - project: (optional) Name of the project the user is part of. (Has to be a String or None, if defined)
        - user_options: (optional) User Options. If a spawner object uses all configured user_options use this config is used.
        
        If configured as a list, the first match will have to pay for a server. If a fallback should be used, configure it without
        user_options as last dict in the return list
        
        This may be a coroutine.
        
        
        Example::
            same_user_credit_values_for_all_users = {
                "name": "default",
                "cap": 100,
                "grant_value": 10,
                "grant_interval": 600,
                "project": None,
            }

            async def credits_user_values_based_on_user_options(user_name, user_groups, is_admin):
                # When a User uses system A, he is forced to use the first credits group.
                # All other spawner configuration (where spawner.user_options["system"] != A) use
                # the generic credit configuration with cap=100.
                ret = [
                    {
                        "name": "system_a_credit",
                        "cap": 20,
                        "grant_value": 5,
                        "grant_interval": 600,
                        "project": None,
                        "user_options": {
                            "system": "A"
                        }
                    },
                    {
                        "name": "default",
                        "cap": 100,
                        "grant_value": 10,
                        "grant_interval": 600,
                        "project": None,
                    }
                ]
                return ret

            async def credits_user_values(user_name, user_groups, is_admin, auth_model):
                ret = {
                    "name": "default",
                    "cap": 100,
                    "grant_value": 10,
                    "grant_interval": 600,
                    "project": None,
                }
                if is_admin:
                    ret["project"] = {
                        "name": "admin",
                        "cap": 1000,
                        "grant_value": 100,
                        "grant_interval": 300
                    }
                elif "community1" in user_groups:
                    ret["project"] = {
                        "name": "community1",
                        "cap": 100,
                        "grant_value": 10,
                        "grant_interval": 300
                    }
                
                return ret

            c.CreditsAuthenticator.credits_user_values = credits_user_values
            # c.CreditsAuthenticator.credits_user_values = credits_user_values_based_on_user_options
        
        
        Default: None
          
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

    def credits_validate_and_update_project(self, _project):
        if not _project.get("name", None):
            self.log.warning(
                "Credits Project requires a 'name'. Fix required for Authenticator.credits_available_projects. Skip project"
            )
            return False
        project_name = _project["name"]
        if "cap" not in _project.keys():
            self.log.warning(
                f"Credits Project requires a 'cap'. Fix required for Authenticator.credits_available_projects. Skip project {project_name}"
            )
            return False
        if "grant_value" not in _project.keys():
            self.log.warning(
                f"Credits Project requires a 'grant_value'. Fix required for Authenticator.credits_available_projects. Skip project {project_name}"
            )
            return False
        if "grant_interval" not in _project.keys():
            self.log.warning(
                f"Credits Project requires a 'grant_interval'. Fix required for Authenticator.credits_available_projects. Skip project {project_name}"
            )
            return False
        if type(_project.get("user_options", {})) != dict:
            self.log.warning(
                f"Credits Project 'user_options' must be a dict. Fix required for Authenticator.credits_available_projects. Skip project {project_name}"
            )
            return False
        if "display_name" not in _project.keys():
            _project["display_name"] = project_name
        return _project

    def match_user_options(self, user_options_spawner, user_options_configured):
        if not user_options_configured:
            return True
        for key, value in user_options_configured.items():
            uo_value = user_options_spawner[key]
            if type(uo_value) == list and len(uo_value) == 1:
                uo_value = uo_value[0]
            if key not in user_options_spawner.keys():
                self.log.debug(
                    f"Key {key} not found in spawner user_options {user_options_spawner}. Return False."
                )
                return False
            if type(value) == list:
                self.log.debug(
                    f"Check if spawner user_option {key} value {uo_value} is in configured list {value}"
                )
                if uo_value not in value:
                    return False
            elif type(value) == str:
                self.log.debug(
                    f"Check if spawner user_option {key} value {uo_value} matches regex pattern {value}"
                )
                try:
                    if re.fullmatch(value, str(uo_value)) is None:
                        self.log.debug(
                            f"Pattern {value} does not match value {uo_value}."
                        )
                        return False
                except re.error:
                    try:
                        if (
                            re.fullmatch(fnmatch.translate(value), str(uo_value))
                            is None
                        ):
                            self.log.debug(
                                f"Pattern {value} does not match value {uo_value}."
                            )
                            return False
                    except re.error:
                        self.log.warning(
                            f"Invalid regex pattern {value} for user_option {key}. Check if strings are equal."
                        )
                        if uo_value != value:
                            return False
            elif type(value) in [int, float, bool]:
                self.log.debug(
                    f"Check if spawner user_option {key} value {uo_value} equals configured value {value}"
                )
                if uo_value != value:
                    return False
            elif type(value) == dict:
                self.log.debug(
                    f"Check if spawner user_option {key} value {uo_value} matches configured dict {value}"
                )
                if not self.match_user_options(uo_value, value):
                    return False
            else:
                self.log.debug(
                    f"Unsupported type {type(value)} for user_option {key}. Check if strings are equal."
                )
                if str(uo_value) != str(value):
                    return False
        return True

    async def credit_reconciliation_task(self):
        while True:
            try:
                tic = time.time()
                now = utcnow(with_tz=False)
                all_credit_users = self.parent.db.query(CreditsUser).all()
                for credit_user in all_credit_users:
                    mem_user = self.user_credits_dict.get(credit_user.name, None)
                    try:
                        if mem_user:
                            # Refresh user auth
                            await self.refresh_user(mem_user)
                    except:
                        self.log.exception(
                            f"Error while refreshing user {credit_user.name} in credit task."
                        )
                    for credits in credit_user.credits_user_values:
                        try:
                            if credits.project:
                                proj_prev_balance = credits.project.balance
                                proj_cap = credits.project.cap
                                proj_updated = False
                                if proj_prev_balance > proj_cap:
                                    credits.project.balance = proj_cap
                                    proj_updated = True
                                elif proj_prev_balance < proj_cap:
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
                                            seconds=grants
                                            * credits.project.grant_interval
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
                                    self.parent.db.commit()
                            prev_balance = credits.balance
                            cap = credits.cap
                            updated = False
                            if prev_balance > cap:
                                credits.balance = cap
                                updated = True
                            else:
                                elapsed = (
                                    now - credits.grant_last_update
                                ).total_seconds()
                                if elapsed >= credits.grant_interval:
                                    updated = True
                                    grants = int(elapsed // credits.grant_interval)
                                    gained = grants * credits.grant_value
                                    credits.balance = min(prev_balance + gained, cap)
                                    credits.grant_last_update += timedelta(
                                        seconds=grants * credits.grant_interval
                                    )
                                    self.log.debug(
                                        f"User {credit_user.name} ({credits.name}): {prev_balance} -> {credits.balance} "
                                        f"(+{gained}, cap {credits.cap})",
                                        extra={
                                            "action": "creditsgained",
                                            "username": credit_user.name,
                                            "creditsname": credits.name,
                                        },
                                    )
                            if updated:
                                self.parent.db.commit()

                            # All projects and user credits are updated.
                            # Now check running spawners and bill credits
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
                                                in credit_user.spawner_bills.keys()
                                            ):
                                                del credit_user.spawner_bills[
                                                    spawner_id_str
                                                ]
                                            continue
                                        if not spawner.ready:
                                            continue
                                        last_billed = None
                                        # When restarting the Hub the last bill timestamp
                                        # will be stored in the database. Use this one.
                                        force_bill = False
                                        if (
                                            spawner_id_str
                                            in credit_user.spawner_bills.keys()
                                        ):
                                            last_billed = datetime.fromisoformat(
                                                credit_user.spawner_bills[
                                                    spawner_id_str
                                                ]
                                            )
                                            # If the last bill timestamp is older than started, it's from
                                            # a previous running lab and should not be used.
                                            if (
                                                last_billed
                                                < spawner.orm_spawner.started
                                            ):
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
                                            user_options = getattr(
                                                spawner, "user_options", {}
                                            )
                                            # Find the correct CreditsUserValues and Project entry for this spawner
                                            user_credits_for_spawner = None
                                            default_cuv = None
                                            for cuv in credit_user.credits_user_values:
                                                if not cuv.user_options:
                                                    default_cuv = cuv
                                                    continue
                                                if user_credits_for_spawner is None:
                                                    match = self.match_user_options(
                                                        user_options,
                                                        cuv.user_options or {},
                                                    )
                                                    self.log.debug(
                                                        f"Test if spawner user_options {user_options} match configured user_options {cuv.user_options or {}} : {match}"
                                                    )
                                                    if match:
                                                        user_credits_for_spawner = cuv
                                                        break

                                            if user_credits_for_spawner is None:
                                                user_credits_for_spawner = default_cuv
                                            if not user_credits_for_spawner:
                                                self.log.warning(
                                                    f"No matching CreditsUserValues found for spawner {spawner._log_name}. Stop Spawner."
                                                )
                                                if spawner.name not in to_stop:
                                                    to_stop.append(spawner.name)
                                                continue
                                            available_balance = 0
                                            project_credits_for_spawner = None
                                            self.log.debug(
                                                f"Using user credits '{user_credits_for_spawner.name}' for spawner {spawner._log_name}"
                                            )
                                            available_balance += (
                                                user_credits_for_spawner.balance
                                            )
                                            prev_balance = (
                                                user_credits_for_spawner.balance
                                            )
                                            if user_credits_for_spawner.project:
                                                project_credits_for_spawner = (
                                                    user_credits_for_spawner.project
                                                )
                                                self.log.debug(
                                                    f"Using project credits '{project_credits_for_spawner.name}' for spawner {spawner._log_name}"
                                                )
                                                available_balance += (
                                                    project_credits_for_spawner.balance
                                                )
                                                proj_prev_balance = (
                                                    project_credits_for_spawner.balance
                                                )

                                            # When force_bill is true we have to make sure to bill the first
                                            # interval as well
                                            bills = max(
                                                int(
                                                    elapsed // spawner._billing_interval
                                                ),
                                                1,
                                            )
                                            cost = bills * spawner._billing_value
                                            if cost > available_balance:
                                                # Stop Server. Not enough credits left for next interval
                                                if spawner.name not in to_stop:
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
                                                if project_credits_for_spawner:
                                                    if (
                                                        cost
                                                        > project_credits_for_spawner.balance
                                                    ):
                                                        proj_cost = (
                                                            project_credits_for_spawner.balance
                                                        )
                                                    else:
                                                        proj_cost = cost
                                                    project_credits_for_spawner.balance -= (
                                                        proj_cost
                                                    )
                                                    cost -= proj_cost
                                                    self.log.debug(
                                                        f"Project {project_credits_for_spawner.name} credits recuded by {proj_cost} ({proj_prev_balance} -> {project_credits_for_spawner.balance}) for server '{spawner._log_name}' ({elapsed}s since last bill timestamp)",
                                                        extra={
                                                            "action": "creditspaid",
                                                            "userid": mem_user.id,
                                                            "username": mem_user.name,
                                                            "servername": spawner.name,
                                                            "projectname": project_credits_for_spawner.name,
                                                        },
                                                    )

                                                user_credits_for_spawner.balance -= cost
                                                if not force_bill:
                                                    last_billed += timedelta(
                                                        seconds=bills
                                                        * spawner._billing_interval
                                                    )
                                                self.log.debug(
                                                    f"User {mem_user.name} credits recuded by {cost} ({prev_balance} -> {user_credits_for_spawner.balance}) for server '{spawner._log_name}' ({elapsed}s since last bill timestamp)",
                                                    extra={
                                                        "action": "creditspaid",
                                                        "userid": mem_user.id,
                                                        "username": mem_user.name,
                                                        "servername": spawner.name,
                                                    },
                                                )
                                                credit_user.spawner_bills[
                                                    spawner_id_str
                                                ] = last_billed.isoformat()
                                                self.parent.db.commit()
                                    except:
                                        self.log.exception(
                                            f"Error while updating user credits for {credit_user} in spawner {spawner._log_name}."
                                        )

                                for spawner_name in to_stop:
                                    self.log.info(
                                        f"Stopping spawner {spawner_name} for user {mem_user.name} due to insufficient credits."
                                    )
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
                self.credits_task_event.set()
                await asyncio.sleep(0)  # give waiters time to proceed
                self.credits_task_event.clear()
                await asyncio.sleep(self.credits_task_interval)

    def credits_append_user(self, user):
        if user.name not in self.user_credits_dict.keys():
            self.user_credits_dict[user.name] = user

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.credits_enabled:
            self.credits_task_event = asyncio.Event()
            inspector = sqlinspect(self.parent.db.bind)
            tables = set(inspector.get_table_names())

            missing = {
                "credits_user",
                "credits_user_values",
                "credits_project",
            } - tables
            if missing:
                self.log.warning("Create Database Tables for JupyterHub Credit Service")
                from sqlalchemy import create_engine

                engine = create_engine(self.parent.db_url)
                Base.metadata.create_all(engine)

            self.credits_task = asyncio.create_task(self.credit_reconciliation_task())

    async def update_user_credit(self, auth_model):
        # Create new ORMUserCredits or ORMProjectCredits entries
        # or Update existing ones, if the config returns values
        # that are not different than values in db
        user_name = auth_model.get("name", None)
        auth_state = auth_model.get("auth_state", {})
        user_groups = auth_model.get("groups", [])
        user_admin = auth_model.get("admin", False)

        async def resolve_value(value):
            if callable(value):
                value = value(self, user_name, user_groups, user_admin, auth_state)
            if inspect.isawaitable(value):
                value = await value
            return value

        grant_last_update = utcnow(with_tz=False)

        credits_user_database = CreditsUser.get_user(self.parent.db, user_name)
        if not credits_user_database:
            # Add CreditsUser entry
            credits_user_database = CreditsUser(name=user_name)
            self.parent.db.add(credits_user_database)
            self.parent.db.commit()

        # Collect configured values
        credits_user_values_configured = await resolve_value(self.credits_user)
        if type(credits_user_values_configured) == dict:
            credits_user_values_configured = [credits_user_values_configured]

        credits_user_values_configured_names = []
        credits_user_values_configured_by_name = {}
        if credits_user_values_configured:
            for x in credits_user_values_configured:
                if "name" not in x.keys():
                    self.log.warning(
                        "User Credit Configuration has no name. Use name default as placeholder."
                    )
                    x["name"] = "default"
                credits_user_values_configured_names.append(x["name"])
                credits_user_values_configured_by_name[x["name"]] = x

        # 1. Keep database entries that are currently configured
        for credits_user_value_db in credits_user_database.credits_user_values:
            if credits_user_value_db.name not in credits_user_values_configured_names:
                self.parent.db.delete(credits_user_value_db)
                self.parent.db.commit()

        for name, credits_user_value in credits_user_values_configured_by_name.items():
            # Does the configuration for the user exist in database, update it. Otherwise create it

            orm_project = None
            configured_project = credits_user_value.get("project", None)
            if configured_project and configured_project.get("name", None):
                project = self.credits_validate_and_update_project(configured_project)
                if not project:
                    continue
                orm_project = CreditsProject.get_project(
                    self.parent.db, configured_project["name"]
                )

                if not orm_project:
                    # Create entry in database
                    project["balance"] = project["cap"]
                    orm_project = CreditsProject(**project)
                    self.parent.db.add(orm_project)
                    self.parent.db.commit()
                else:
                    # Check + Update project
                    prev_project_balance = orm_project.balance
                    prev_project_cap = orm_project.cap
                    prev_project_grant_value = orm_project.grant_value
                    prev_project_grant_interval = orm_project.grant_interval
                    proj_updated = False
                    if prev_project_cap != project["cap"]:
                        proj_updated = True
                        orm_project.cap = project["cap"]
                        if prev_project_balance > orm_project.cap:
                            orm_project.balance = orm_project.cap
                    if prev_project_grant_value != project["grant_value"]:
                        proj_updated = True
                        orm_project.grant_value = project["grant_value"]
                    if prev_project_grant_interval != project["grant_interval"]:
                        proj_updated = True
                        orm_project.grant_interval = project["grant_interval"]
                    if proj_updated:
                        self.parent.db.add(orm_project)
                        self.parent.db.commit()

            database_entry = CreditsUser.get_user(
                self.parent.db, user_name
            ).credits_user_values
            database_entry = [x for x in database_entry if x.name == name]
            if database_entry:
                database_entry = database_entry[0]
                database_entry.cap = credits_user_value.get("cap")
                database_entry.grant_value = credits_user_value.get("grant_value")
                database_entry.grant_interval = credits_user_value.get("grant_interval")
                database_entry.user_options = credits_user_value.get(
                    "user_options", None
                )
                if database_entry.balance > database_entry.cap:
                    database_entry.balance = database_entry.cap
                database_entry.project = orm_project
                # Add existing DB Project to existing userconfig entry
            else:
                database_entry = CreditsUserValues(
                    name=name,
                    balance=credits_user_value["cap"],
                    cap=credits_user_value["cap"],
                    grant_value=credits_user_value["grant_value"],
                    grant_interval=credits_user_value["grant_interval"],
                    grant_last_update=grant_last_update,
                    user_options=credits_user_value.get("user_options", None),
                    credits_user=credits_user_database,
                    project=orm_project,
                )
            self.parent.db.add(database_entry)
            self.parent.db.commit()

    async def run_post_auth_hook(self, handler, auth_model):
        auth_model = await super().run_post_auth_hook(handler, auth_model)
        if self.credits_enabled:
            orm_user = ORMUser.find(self.parent.db, auth_model["name"])
            # If it's a new user there won't be an entry.
            # This case will be handled in .add_user()
            if orm_user:
                if "groups" not in auth_model:
                    groups = [x.name for x in orm_user.groups]
                    auth_model["groups"] = groups
                auth_model["admin"] = orm_user.admin or False
            await self.update_user_credit(auth_model)
        return auth_model
