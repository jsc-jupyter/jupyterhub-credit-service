from pathlib import Path

from jupyterhub.handlers import default_handlers

from .apihandlers import (
    CreditsAPIHandler,
    CreditsProjectAPIHandler,
    CreditsSSEAPIHandler,
    CreditsUserAPIHandler,
)
from .authenticator import CreditsAuthenticator  # noqa: F401
from .spawner import CreditsSpawner  # noqa: F401

template_path = [str(Path(__path__[0]) / "templates")]

default_handlers.append((r"/api/credits", CreditsAPIHandler))
default_handlers.append((r"/api/credits/sse", CreditsSSEAPIHandler))
default_handlers.append((r"/api/credits/user/([^/]+)", CreditsUserAPIHandler))
default_handlers.append((r"/api/credits/project/([^/]+)", CreditsProjectAPIHandler))
