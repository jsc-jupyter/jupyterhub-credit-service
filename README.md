# JupyterHub Credit Service

[![Documentation](https://img.shields.io/badge/Documentation-passed-green)](https://jsc-jupyter.github.io/jupyterhub-credit-service/)
[![PyPI Test Action](https://github.com/jsc-jupyter/jupyterhub-credit-service/actions/workflows/pytest.yml/badge.svg?branch=main)](https://github.com/jsc-jupyter/jupyterhub-credit-service/actions/workflows/pytest.yml)
[![PyPI](https://img.shields.io/pypi/v/jupyterhub-credit-service)](https://pypi.org/project/jupyterhub-credit-service/)

---

## Overview

The **JupyterHub Credit Service** is a python package that can be installed as an extension to JupyterHub. It introduces a lightweight, flexible system to limit **resource consumption** on a **per-user** and/or **per-project** model.

It enables administrators to control how long users can use computational environments, and how shared project resources are allocated — all without complex accounting or billing systems.

<div style="text-align: center;">
  <img src="https://jsc-jupyter.github.io/jupyterhub-credit-service/images/image_home.png" alt="JupyterHub" style="width: 100%;">
</div>

---

## Installation

You can install the package directly from PyPI:

```bash
pip install jupyterhub-credit-service
```

---

## Configuration

For detailed information, please visit the [documentation site](https://jsc-jupyter.github.io/jupyterhub-credit-service/).

Example `jupyterhub_config.py`:

```python
import jupyterhub_credit_service

# Configure Authenticator
from oauthenticator.generic import GenericOAuthenticator
# Use any Authenticator you usually use together with the CreditsAuthenticator
class MixinAuthenticator(GenericOAuthenticator, jupyterhub_credit_service.CreditsAuthenticator):
    pass

c.JupyterHub.authenticator_class = MixinAuthenticator

# Different users may get different amount of credits
def user_cap(username, user_groups=[], is_admin=False):
    if username.endswith("mycompany.org"):
        return 1000
    elif username.endswith("googlemail.com") or username.endswith("gmail.com"):
        return 30
    return 100

c.MixinAuthenticator.credits_user_cap = user_cap  # may be a callable or integer
c.MixinAuthenticator.credits_user_grant_value = 5 # may be a callable or integer
c.MixinAuthenticator.credits_user_grant_interval = 600 # Gain 5 credits every 10 minutes, may be a callable or integer

c.MixinAuthenticator.userinfo_url = ... # your normal configuration


# Configure Spawner
import kubespawner
# You can reuse the "KubeSpawner" name so you don't have to change your other configs
class KubeSpawner(kubespawner.KubeSpawner, jupyterhub_credit_service.CreditsSpawner):
    pass

def get_billing_value(spawner):
    # Costs gpus*10 credits + 5 credits, per billing_interval
    billing_value = 5
    if "gpus" in spawner.user_options.keys():
        billing_value += spawner.user_options["gpus"] * 10
    return billing_value

c.JupyterHub.spawner_class = KubeSpawner
c.KubeSpawner.billing_value = get_billing_value # may be a callable or integer
c.KubeSpawner.billing_interval = 600 # Pay credits depending on gpus usage every 10 minutes, may be a callable or integer

# Show JupyterHub Credits in the Header in your frontend
c.JupyterHub.template_paths = jupyterhub_credit_service.template_paths
```
