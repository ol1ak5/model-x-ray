import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.llm import build_chat_model
from model_x_ray.memory import sqlite_checkpointer, sqlite_store
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource


def setting(name: str, default: str) -> str:
    return os.environ.get(name) or default


def app_from_env() -> FastAPI:
    load_dotenv()
    models_dir = Path(setting("MODEL_X_RAY_MODELS_DIR", "demo_models"))
    if not models_dir.is_dir():
        raise ValueError(f"The models folder {models_dir} does not exist; create it and put .xlsx models in it, or set MODEL_X_RAY_MODELS_DIR")
    files = {path.relative_to(models_dir).with_suffix("").as_posix(): path for path in sorted(models_dir.rglob("*.xlsx"))}
    source = XlsxSource(files)
    sandbox = XlsxSandbox(source, Path(setting("MODEL_X_RAY_OUTPUT_DIR", "corrected")))
    models = AgentModels(
        llm=build_chat_model(role="investigator"),
        verifier=build_chat_model(role="verifier"),
        locator=build_chat_model(role="locate"),
        mapper=build_chat_model(role="mapper"),
        explainer=build_chat_model(role="explain"),
    )
    checkpointer = sqlite_checkpointer(setting("MODEL_X_RAY_CHECKPOINTS", "checkpoints.db"))
    cap = UsageCap(per_visitor=int(setting("DEMO_MAX_PER_VISITOR", "5")), total=int(setting("DEMO_MAX_PER_DAY", "100")))
    origins = [origin.strip() for origin in setting("MODEL_X_RAY_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]
    store = sqlite_store(setting("MODEL_X_RAY_MEMORY", "memory.db"))
    uploads = Path(setting("MODEL_X_RAY_UPLOAD_DIR", "uploads"))
    upload_ttl = float(setting("MODEL_X_RAY_UPLOAD_TTL", "1800"))
    return create_app(source, sandbox, models, checkpointer, cap, origins, store, uploads, upload_ttl, copy_dir=Path(setting("MODEL_X_RAY_OUTPUT_DIR", "corrected")), copy_ttl=float(setting("MODEL_X_RAY_COPY_TTL", "1800")))
