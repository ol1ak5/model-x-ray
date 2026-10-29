import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from model_x_ray.api import AgentModels, UsageCap, create_app
from model_x_ray.llm import build_chat_model
from model_x_ray.memory import sqlite_checkpointer, sqlite_store
from model_x_ray.spreadsheet.sandbox import XlsxSandbox
from model_x_ray.spreadsheet.source import XlsxSource


class StartupError(RuntimeError):
    pass


def setting(name: str, default: str) -> str:
    return os.environ.get(name) or default


def writable(name: str) -> str:
    if not os.environ.get("VERCEL"):
        return name
    folder = Path(tempfile.gettempdir()) / "model-x-ray"
    folder.mkdir(parents=True, exist_ok=True)
    return str(folder / name)


def unusable_folder(name: str, folder: Path) -> str | None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return f"{name} points at {folder}, which cannot be created ({error.strerror}). Point it at a folder the server can write."
    if not os.access(folder, os.W_OK):
        return f"{name} points at {folder}, which cannot be written by this user. Point it at a folder the server can write."
    return None


def startup_problems(models_dir: Path, output_dir: Path, upload_dir: Path, checkpoints: Path, memory: Path) -> list[str]:
    problems = []
    if not os.environ.get("NEBIUS_API_KEY"):
        problems.append("NEBIUS_API_KEY is not set. Copy .env.example to .env and set NEBIUS_API_KEY to your Nebius Token Factory key, or export it before starting.")
    if not models_dir.is_dir():
        problems.append(f"MODEL_X_RAY_MODELS_DIR points at {models_dir}, which does not exist. Create it with .xlsx models in it, or use the demo_models folder that ships with the repository.")
    elif not any(models_dir.rglob("*.xlsx")):
        problems.append(f"MODEL_X_RAY_MODELS_DIR points at {models_dir}, which holds no .xlsx models. Put a workbook there, or use the demo_models folder that ships with the repository.")
    for name, folder in (("MODEL_X_RAY_OUTPUT_DIR", output_dir), ("MODEL_X_RAY_UPLOAD_DIR", upload_dir)):
        complaint = unusable_folder(name, folder)
        if complaint:
            problems.append(complaint)
    for name, path in (("MODEL_X_RAY_CHECKPOINTS", checkpoints), ("MODEL_X_RAY_MEMORY", memory)):
        complaint = unusable_folder(name, path.parent)
        if complaint:
            problems.append(complaint)
    return problems


def refuse_to_start(problems: list[str]) -> StartupError:
    lines = "\n".join(f"  - {problem}" for problem in problems)
    return StartupError(f"Model X-Ray cannot start, because {len(problems)} setting{'s' if len(problems) > 1 else ''} would not work:\n\n{lines}\n\nNothing was started and no request was served. Fix the settings above, then start again.")


def app_from_env() -> FastAPI:
    load_dotenv()
    models_dir = Path(setting("MODEL_X_RAY_MODELS_DIR", "demo_models"))
    output_dir = Path(setting("MODEL_X_RAY_OUTPUT_DIR", writable("corrected")))
    upload_dir = Path(setting("MODEL_X_RAY_UPLOAD_DIR", writable("uploads")))
    checkpoints = Path(setting("MODEL_X_RAY_CHECKPOINTS", writable("checkpoints.db")))
    memory = Path(setting("MODEL_X_RAY_MEMORY", writable("memory.db")))
    problems = startup_problems(models_dir, output_dir, upload_dir, checkpoints, memory)
    if problems:
        raise refuse_to_start(problems)
    files = {path.relative_to(models_dir).with_suffix("").as_posix(): path for path in sorted(models_dir.rglob("*.xlsx"))}
    source = XlsxSource(files)
    sandbox = XlsxSandbox(source, output_dir)
    models = AgentModels(
        llm=build_chat_model(role="investigator"),
        verifier=build_chat_model(role="verifier"),
        locator=build_chat_model(role="locate"),
        mapper=build_chat_model(role="mapper"),
        explainer=build_chat_model(role="explain"),
    )
    checkpointer = sqlite_checkpointer(str(checkpoints))
    cap = UsageCap(per_visitor=int(setting("DEMO_MAX_PER_VISITOR", "5")), total=int(setting("DEMO_MAX_PER_DAY", "100")))
    origins = [origin.strip() for origin in setting("MODEL_X_RAY_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]
    store = sqlite_store(str(memory))
    upload_ttl = float(setting("MODEL_X_RAY_UPLOAD_TTL", "1800"))
    ask_cap = UsageCap(per_visitor=int(setting("DEMO_MAX_QUESTIONS_PER_VISITOR", "30")), total=int(setting("DEMO_MAX_QUESTIONS_PER_DAY", "500")), noun="questions")
    return create_app(source, sandbox, models, checkpointer, cap, origins, store, upload_dir, upload_ttl, copy_dir=output_dir, copy_ttl=float(setting("MODEL_X_RAY_COPY_TTL", "1800")), ask_cap=ask_cap)
