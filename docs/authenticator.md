# CreditsAuthenticator

This module forms the core of the **JupyterHub Credit Service**. At every interval defined by `Authenticator.credits_task_interval`, the service updates the credit balances for all users. If a user's available credits are insufficient to maintain a running Jupyter server, that server is automatically stopped. This mechanism enables administrators to enforce per-user resource limits and ensure fair usage across the deployment.  

## Configure Credits per User

A user's credit configuration is defined by three main parameters:

- **credits_user_cap**: The maximum number of credits a user can hold. Default: 100
- **credits_user_grant_value**: The number of credits granted to a user every `credits_user_grant_interval` seconds. Default: 10
- **credits_user_grant_interval**: The time interval, in seconds, at which users receive their `credits_user_grant_value` credits. Default: 600

Each of these parameters can be specified either as an integer value or as a callable function that dynamically determines the configuration.

```python
async def user_cap(user_name, user_groups, is_admin):
    if user_name == "max":
        return 150
    return 100

def user_grant_value(user_name, user_groups, is_admin):
    if is_admin:
        return 20
    return 10

def user_grant_interval(user_name, user_groups, is_admin):
    if "premium" in user_groups:
        return 300  # grant every 5 minutes
    return 600  # default 10 minutes

# Use callable functions (async or sync), or integer values
c.CreditsAuthenticator.credits_user_cap = user_cap
c.CreditsAuthenticator.credits_user_grant_value = user_grant_value
c.CreditsAuthenticator.credits_user_grant_interval = user_grant_interval
```

## Configure Projects

The JupyterHub Credit Service also supports shared credit pools through **projects**. Projects represent groups or communities that share a collective credit balance. When a user belongs to a project, their usage draws from the project’s credits first, before using their individual credit balance.

A project requires a **name**, along with the same core parameters as the user credit configuration:  
- **cap**  
- **grant_value**  
- **grant_interval**

> Each user can belong to **only one** project.  
> To exclude a user from any project, return **None** or omit the `credits_user_project` configuration entirely.

To configure projects use these parameters:
- **credits_available_projects**: Define a list of available projects a user can be part of. Default: []
- **credits_user_project**: Callable to define a name of a project a user is part of. Default: None

```python

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

c.CreditsAuthenticator.credits_available_projects = available_projects # List of dicts or a (async) callable

def credits_user_project(user_name, user_groups, is_admin):
    if "community1" in user_groups:
        return "community1"
    return None

c.CreditsAuthenticator.credits_user_project = credits_user_project # Must be a callable

```

## Other Configurations

- **credits_enabled**: Enables or disables the credit system entirely.  
  *Default: true*

- **credits_task_interval**: Defines the interval, in seconds, at which the background credit management task executes.  
  *Default: 60*

- **credits_task_post_hook**: An optional callback function executed after each **billing interval**.  
  *Default: None*


## Implementation / Credit Logic

The main process driving the system is the `Authenticator.credit_reconciliation_task()` function.  
This background task runs every `Authenticator.credits_task_interval` seconds and performs the following actions:

- **Add Project Credits** based on project-specific configuration values.  
- **Add User Credits** based on user-specific configuration values.  
- **Deduct Project/User Credits** for active servers, according to their spawner-specific billing rules.

Whenever `Authenticator.add_user` (triggered for users not yet registered in JupyterHub) or `Authenticator.run_post_auth_hook` (typically called during login or authentication refresh) is executed, the user’s configuration is updated.  
This mechanism ensures that administrators can modify and apply configuration updates for existing users seamlessly.
