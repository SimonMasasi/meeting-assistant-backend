from src.modules.auth.views import auth_router
from src.modules.settings.views import settings_router
from src.modules.uploads.views import uploads_router
from src.utils.open_api_routes import open_api_router
from src.modules.meetings.views import meeting_router

routes  = [
    auth_router,
    settings_router,
    uploads_router,
    open_api_router,
    meeting_router
]