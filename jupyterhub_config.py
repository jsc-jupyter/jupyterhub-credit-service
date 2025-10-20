c = get_config()  # noqa


from jupyterhub.auth import DummyAuthenticator
from jupyterhub.spawner import SimpleLocalProcessSpawner

from jupyterhub_credit_service import template_paths
from jupyterhub_credit_service.authenticator import CreditsAuthenticator
from jupyterhub_credit_service.spawner import CreditsSpawner

# Show current User Credits in Frontend
c.JupyterHub.template_paths = template_paths


class SimpleLocalProcessCreditsSpawner(SimpleLocalProcessSpawner, CreditsSpawner):
    pass


class DummyCreditsAuthenticator(DummyAuthenticator, CreditsAuthenticator):
    pass


c.JupyterHub.authenticator_class = DummyCreditsAuthenticator
c.JupyterHub.spawner_class = SimpleLocalProcessCreditsSpawner
# c.JupyterHub.spawner_class = SimpleLocalProcessSpawner

c.JupyterHub.log_level = 10


def user_cap(user_name, user_groups, is_admin):
    if user_name == "max":
        return 150
    return 100


available_projects = [
    {"name": "Project1", "cap": 500, "grant_interval": 60, "grant_value": 50}
]


def user_project(user_name, *args):
    return "Project1"


c.DummyCreditsAuthenticator.admin_users = ["admin"]
c.DummyCreditsAuthenticator.credits_user_cap = user_cap
c.DummyCreditsAuthenticator.credits_available_projects = available_projects
c.DummyCreditsAuthenticator.credits_user_project = user_project

c.DummyCreditsAuthenticator.credits_task_interval = 5

# c.DummyCreditsAuthenticator.credits_task_interval = 10
c.DummyCreditsAuthenticator.credits_user_grant_interval = 60
c.DummyCreditsAuthenticator.credits_user_grant_value = 30


def get_billing_value(spawner):
    values = {"normal": 10, "power": 20}
    mode = spawner.user_options.get("mode", [None])[0]
    return values[mode]


c.SimpleLocalProcessCreditsSpawner.billing_value = get_billing_value
c.SimpleLocalProcessCreditsSpawner.billing_interval = 10
c.SimpleLocalProcessCreditsSpawner.cmd = [
    "/opt/miniforge3/envs/jupyterhub-credit-service/bin/jupyterhub-singleuser"
]
c.SimpleLocalProcessCreditsSpawner.options_form = """
Choose a mode:
<select name="mode">
    <option value="normal">Normal Mode (costs 10 credits every 10 minutes)</option>
    <option value="power">Power Mode (costs 20 credits every 10 minutes)</option>
</select>
"""
