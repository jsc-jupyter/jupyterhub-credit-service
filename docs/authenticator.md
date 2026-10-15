# CreditsAuthenticator

This module forms the core of the **JupyterHub Credit Service**. At every interval defined by `Authenticator.credits_task_interval`, the service updates the credit balances for all users. If a user's available credits are insufficient to maintain a running Jupyter server, that server is automatically stopped. This mechanism enables administrators to enforce per-user resource limits and ensure fair usage across the deployment.  

## Configure Credits per User

A user's credit configuration is defined by a few main parameters:

- **name**: Name of the credits configuration.
- **cap**: The maximum number of credits a user can hold. Default: 100
- **grant_value**: The number of credits granted to a user every `credits_user_grant_interval` seconds. Default: 10
- **grant_interval**: The time interval, in seconds, at which users receive their `credits_user_grant_value` credits. Default: 600
  
The JupyterHub Credit Service also supports shared credit pools through **projects**. Projects represent groups or communities that share a collective credit balance. When a user belongs to a project, their usage draws from the project’s credits first, before using their individual credit balance.  
  
Furthermore, administrators can configure multiple credit configurations based on the user_options. E.g. if the user starts a Jupyter Server on system A it uses a different pool than starting on system B.
  
Simple example with projects:  
  
```python
async def credits_user(user_name, user_groups, is_admin, auth_model):
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

# Use callable functions (async or sync), dict or list of dicts
c.CreditsAuthenticator.credits_user = credits_user
```
  
Credits based on user_options:  
  
```python
async def credits_user(user_name, user_groups, is_admin, auth_model):
    ret = [
        {
            "name": "SystemA",
            "cap": 300,
            "grant_value": 10,
            "grant_interval": 600,
            "project": None,
            "user_options": {
                "system": "A"
            }
        },
        {
            "name": "SystemB",
            "cap": 200,
            "grant_value": 10,
            "grant_interval": 600,
            "project": None,
            "user_options": {
                "system": "B"
            }
        },
        {
            "name": "Fallback / default",
            "cap": 200,
            "grant_value": 10,
            "grant_interval": 600,
            "project": None
        }
    ]
    return ret

# Use callable functions (async or sync), dict or list of dicts
c.CreditsAuthenticator.credits_user = credits_user
```

## Other Configurations

- **credits_enabled**: Enables or disables the credit system entirely.  
  *Default: true*

- **credits_task_interval**: Defines the interval, in seconds, at which the background credit management task executes.  
  *Default: 60*

- **credits_task_post_hook**: An optional callback function executed after each **billing interval**.  
  *Default: None*

- **credits_grant_sync_time**: Optional timestamp to ensure users gain credits at this timestamp (e.g. each morning at 7AM, so users don't start the day without credits). **Format: "HH:MM" (24-hour format, UTC)**
  *Default: None*

## Implementation / Credit Logic

The main process driving the system is the `Authenticator.credit_reconciliation_task()` function.  
This background task runs every `Authenticator.credits_task_interval` seconds and performs the following actions:

- **Add Project Credits** based on project-specific configuration values.  
- **Add User Credits** based on user-specific configuration values.  
- **Deduct Project/User Credits** for active servers, according to their spawner-specific billing rules.

Whenever `Authenticator.add_user` (triggered for users not yet registered in JupyterHub) or `Authenticator.run_post_auth_hook` (typically called during login or authentication refresh) is executed, the user’s configuration is updated.  
This mechanism ensures that administrators can modify and apply configuration updates for existing users seamlessly.
