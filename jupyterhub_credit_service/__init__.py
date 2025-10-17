from jupyterhub.handlers import default_handlers

from .apihandlers import CreditsAPIHandler, CreditsProjectAPIHandler, CreditsUserAPIHandler

from .authenticator import CreditsAuthenticator
from .spawner import CreditsSpawner

default_handlers.append((r"/api/credits", CreditsAPIHandler))
default_handlers.append((r"/api/credits/user/([^/]+)", CreditsUserAPIHandler))
default_handlers.append((r"/api/credits/project/([^/]+)", CreditsProjectAPIHandler))
