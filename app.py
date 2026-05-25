from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference
from src.shared.database import run_migrations
from src.shared.routes import routes
from config import SETTINGS
import uvicorn


app = FastAPI()
run_migrations()

for router in routes:
    app.include_router(router)


@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        # Your OpenAPI document
        openapi_url=app.openapi_url,
        # Avoid CORS issues (optional)
        scalar_proxy_url="https://proxy.scalar.com",
    )
    
    
if __name__ == "__main__":
    uvicorn.run(app, host=SETTINGS.APP_HOST, port=SETTINGS.APP_PORT , log_level="debug" if SETTINGS.DEBUG else "info")