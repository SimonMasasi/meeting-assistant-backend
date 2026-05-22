from fastapi import FastAPI
from scalar_fastapi import get_scalar_api_reference
from src.shared.database import create_db_and_tables
from routes import routes


app = FastAPI()
create_db_and_tables()

for router in routes:
    app.include_router(router)



@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}

@app.get("/scalar", include_in_schema=False)
async def scalar_html():
    return get_scalar_api_reference(
        # Your OpenAPI document
        openapi_url=app.openapi_url,
        # Avoid CORS issues (optional)
        scalar_proxy_url="https://proxy.scalar.com",
    )