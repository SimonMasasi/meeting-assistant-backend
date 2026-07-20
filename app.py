from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.shared.database import run_migrations
from src.shared.routes import routes
from src.utils.open_api_routes import custom_openapi
from src.utils.startup_banner import log_startup_banner
from config import SETTINGS
import uvicorn


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_startup_banner()
    yield


app = FastAPI(lifespan=lifespan)
run_migrations()

for router in routes:
    app.include_router(router)
    
app.openapi = lambda: custom_openapi(app)

if __name__ == "__main__":
    uvicorn.run("app:app", host=SETTINGS.APP_HOST, port=SETTINGS.APP_PORT , log_level="debug" if SETTINGS.DEBUG else "info" , reload=SETTINGS.DEBUG)