from fastapi import APIRouter, FastAPI
from fastapi.openapi.utils import get_openapi
from scalar_fastapi import get_scalar_api_reference

open_api_router = APIRouter(tags=["openapi"])



def custom_openapi(app: FastAPI):
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


@open_api_router.get("/scalar", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        openapi_url="/openapi.json",
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