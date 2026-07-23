from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.modules.uploads.tus_views import TUS_EXPOSED_HEADERS, cleanup_expired_tus_uploads
from src.shared.database import run_migrations
from src.shared.routes import routes
from src.utils.open_api_routes import custom_openapi
from src.utils.startup_banner import log_startup_banner
from config import SETTINGS
import uvicorn


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_startup_banner()
    # Abandoned resumable uploads hold buffers of up to TUS_MAX_UPLOAD_SIZE_BYTES
    # each, so reap the expired ones before serving.
    cleanup_expired_tus_uploads()
    yield


app = FastAPI(lifespan=lifespan)
run_migrations()

# tus clients read the upload offset off the response headers; without exposing
# them a browser client cannot resume.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=TUS_EXPOSED_HEADERS,
)

for router in routes:
    app.include_router(router)
    
app.openapi = lambda: custom_openapi(app)

if __name__ == "__main__":
    uvicorn.run("app:app", host=SETTINGS.APP_HOST, port=SETTINGS.APP_PORT , log_level="debug" if SETTINGS.DEBUG else "info" , reload=SETTINGS.DEBUG)