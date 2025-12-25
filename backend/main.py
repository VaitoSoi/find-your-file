import os
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from lib.db import init
from router import entry_router, user_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init()
    yield
    


app = FastAPI(
    title="Find your File Backend",
    description="A simple API to manage your file, using S3-compatible service as object storage",
    lifespan=lifespan,
)

api_router = APIRouter()
api_router.include_router(entry_router)
api_router.include_router(user_router)

ENV = os.getenv("ENV", "DEV")
if ENV == "PROD":
    app.include_router(api_router, prefix="/api")

    if os.path.exists("static/assets"):
        app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        file_path = os.path.join("static", full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="not found")

        return FileResponse("static/index.html")

else:
    app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
