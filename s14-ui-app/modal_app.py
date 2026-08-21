"""Modal deployment for Atlas (Session 14, Part 2).

Atlas holds no provider credentials. It reaches the gateway over ordinary HTTP,
so the only thing it needs to know is where the gateway lives.

    modal deploy modal_app.py

GLC_BASE_URL must point at the deployed glc_v3 gateway. Set it here rather than
in a Secret, because a URL is not a credential and keeping it visible makes the
seam obvious to anyone reading the deployment.
"""

import os
from pathlib import Path

import modal

app = modal.App("atlas-ui")

HERE = Path(__file__).parent

# The gateway URL is injected at build time. Override before deploying:
#   GLC_URL=https://<workspace>--glc-v3-gateway-fastapi-app.modal.run modal deploy modal_app.py
GLC_URL = os.getenv("GLC_URL", "https://example--glc-v3-gateway-fastapi-app.modal.run")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi>=0.115",
        "uvicorn[standard]>=0.30",
        "httpx>=0.27",
        "pydantic>=2.7",
    )
    .env(
        {
            "GLC_BASE_URL": GLC_URL,
            "ATLAS_PROVIDER": "moonshot",
            # kimi-k3 spends roughly 2700 output tokens reasoning before it
            # emits a character. A smaller cap returns stop_reason=max_tokens
            # with an empty string, which reads as a broken model.
            "ATLAS_MAX_TOKENS": "6000",
        }
    )
    .add_local_file(str(HERE / "app.py"), remote_path="/root/app.py")
    .add_local_file(str(HERE / "client.html"), remote_path="/root/client.html")
)


@app.function(
    image=image,
    min_containers=0,
    timeout=600,  # a composition turn on a reasoning model is slow
)
@modal.asgi_app()
def web():
    import sys

    sys.path.insert(0, "/root")
    from app import app as atlas

    return atlas
