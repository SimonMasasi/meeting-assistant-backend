from fastapi import FastAPI
from src.shared.database import run_migrations
from src.shared.routes import routes
from src.utils.open_api_routes import custom_openapi
from config import SETTINGS
import uvicorn


app = FastAPI()
run_migrations()



for router in routes:
    app.include_router(router)
    
app.openapi = lambda: custom_openapi(app)


if __name__ == "__main__":
    uvicorn.run(app, host=SETTINGS.APP_HOST, port=SETTINGS.APP_PORT , log_level="debug" if SETTINGS.DEBUG else "info")