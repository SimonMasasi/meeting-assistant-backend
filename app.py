from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from scalar_fastapi import get_scalar_api_reference
from src.shared.database import run_migrations
from src.shared.routes import routes
from config import SETTINGS
import uvicorn


app = FastAPI()
run_migrations()

for router in routes:
    app.include_router(router)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
    }
    schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url=app.openapi_url,
        scalar_proxy_url="https://proxy.scalar.com",
        authentication={
            "preferredSecurityScheme": "BearerAuth",
            "http": {
                "bearer": {
                    "token": "",
                }
            },
        },
        persist_auth=True,
    )
    
    
if __name__ == "__main__":
    uvicorn.run(app, host=SETTINGS.APP_HOST, port=SETTINGS.APP_PORT , log_level="debug" if SETTINGS.DEBUG else "info")