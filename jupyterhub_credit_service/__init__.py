from jupyterhub.handlers import default_handlers

from .handlers import CreditsAPIHandler

default_handlers.append((r"/api/credits", CreditsAPIHandler))
default_handlers.append((r"/api/credits/([^/]+)", CreditsAPIHandler))
