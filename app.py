from pathlib import Path

from model_x_ray.server import app_from_env

app = app_from_env()

if Path("frontend/dist/index.html").is_file():
    app.frontend("/", directory="frontend/dist")
