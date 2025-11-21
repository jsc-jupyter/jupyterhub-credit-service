from pathlib import Path

from jupyterhub.handlers import default_handlers

from .apihandlers import (
    CreditsAPIHandler,
    CreditsAPIHealthHandler,
    CreditsProjectAPIHandler,
    CreditsSSEAPIHandler,
    CreditsSSEServerAPIHandler,
    CreditsStopServerAPIHandler,
    CreditsUserAPIHandler,
)
from .authenticator import CreditsAuthenticator  # noqa: F401
from .spawner import CreditsSpawner  # noqa: F401

template_paths = [str(Path(__path__[0]) / "templates")]

default_handlers.append((r"/api/credits", CreditsAPIHandler))
default_handlers.append((r"/api/credits/health", CreditsAPIHealthHandler))
default_handlers.append((r"/api/credits/sse", CreditsSSEAPIHandler))
default_handlers.append((r"/api/credits/sseserver/([^/]+)", CreditsSSEServerAPIHandler))
default_handlers.append(
    (r"/api/credits/sseserver/([^/]+)/([^/]+)", CreditsSSEServerAPIHandler)
)
default_handlers.append(
    (r"/api/credits/stopserver/([^/]+)", CreditsStopServerAPIHandler)
)
default_handlers.append(
    (r"/api/credits/stopserver/([^/]+)/([^/]+)", CreditsStopServerAPIHandler)
)
default_handlers.append((r"/api/credits/user/([^/]+)/([^/]+)", CreditsUserAPIHandler))
default_handlers.append((r"/api/credits/project/([^/]+)", CreditsProjectAPIHandler))
