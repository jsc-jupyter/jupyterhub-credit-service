# CreditsSpawner

The **CreditsSpawner** extends the standard JupyterHub Spawner class by introducing a credit-based accounting system for server usage.  
Each server instance can be assigned a specific **credit cost**, allowing administrators to define how many credits a user (or their project) must spend to start and maintain a running server.

It also prevents server startup when insufficient credits are available, enforcing usage policies in real time.


## Configure Costs per Spawner

Each spawner can define its own credit consumption model through two key parameters:

- **billing_value**: The number of credits deducted from a user’s (or project’s) account every `billing_interval` seconds while their server remains active.  
  *Default: 10*

- **billing_interval**: The time interval, in seconds, at which the billing process occurs for a running server.  
  *Default: 600*

Both parameters can be provided as static integer values or as callable functions that dynamically calculate the configuration at runtime.  
This flexibility allows administrators to define customized billing rules depending on factors such as server size, resource profile, or user group.

```python
def get_billing_value(spawner):
    values = {
        "normal": 5,
        "expensive": 10,
    }
    mode = spawner.user_options.get("mode", "normal")
    return values.get(mode, 5)

c.CreditsSpawner.billing_value = get_billing_value

def get_billing_interval(spawner):
    if spawner.user_options.get("slowinterval"):
        return 1200
    return 600

c.CreditsSpawner.billing_interval = get_billing_interval
```


## Implementation

Within `Spawner.run_pre_spawn_hook()`, the spawner defines both **billing_value** and **billing_interval** for the current server instance.  
Before the server starts, the system verifies whether the user (or their associated project) has sufficient credits to cover the initial cost.  

If the available credits are insufficient, a `CreditsException` is raised, preventing the server from launching and displaying a clear, informative error message to the user.  
This ensures that users cannot exceed their allocated credit limits and provides immediate feedback when resources cannot be started due to credit constraints.

## User information

The CreditsSpawner shows the required credits and billing interval when starting the Jupyter Server.

<div style="text-align: center;">
  <img src="https://jsc-jupyter.github.io/jupyterhub-credit-service/images/image_spawn.png" alt="JupyterHub Spawner" style="width: 70%;">
</div>