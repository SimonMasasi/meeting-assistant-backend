from src.modules.auth.views import auth_router
from src.modules.settings.views import settings_router
from src.modules.uploads.views import uploads_router

routes  = [
    auth_router,
    settings_router,
    uploads_router
]