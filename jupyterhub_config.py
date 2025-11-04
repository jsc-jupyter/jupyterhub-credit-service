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

c.JupyterHub.log_level = 10


def credits_user(user_name, user_groups, is_admin, auth_state):
    if user_name == "e":
        return [
            {
                "cap": 150,
                "grant_interval": 30,
                "grant_value": 20,
            },
            {
                "name": "SystemX",
                "cap": 150,
                "grant_interval": 30,
                "grant_value": 20,
                "user_options": {"system": "X"},
                "project": {
                    "name": "ProjectX",
                    "cap": 500,
                    "grant_interval": 60,
                    "grant_value": 50,
                },
            },
        ]
    return [
        {
            "name": "SystemA",
            "cap": 1500,
            "grant_interval": 30,
            "grant_value": 20,
            "user_options": {"system": "A"},
        },
        {
            "name": "SystemB",
            "cap": 1500,
            "grant_interval": 30,
            "grant_value": 20,
            "user_options": {"system": "B"},
        },
    ]


c.DummyCreditsAuthenticator.admin_users = ["admin"]
c.DummyCreditsAuthenticator.credits_user = credits_user
c.DummyCreditsAuthenticator.credits_task_interval = 5


def get_billing_value(spawner):
    return 110


c.SimpleLocalProcessCreditsSpawner.billing_value = get_billing_value
c.SimpleLocalProcessCreditsSpawner.billing_interval = 10
c.SimpleLocalProcessCreditsSpawner.cmd = [
    "/opt/miniforge3/envs/jupyterhub-credits-service/bin/jupyterhub-singleuser"
]
c.SimpleLocalProcessCreditsSpawner.options_form = """
Choose a system:
<select name="system">
    <option value="A">A</option>
    <option value="B">B</option>
</select>
"""
