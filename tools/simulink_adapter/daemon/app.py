from __future__ import annotations

from fastapi import FastAPI

try:
    from .config import get_daemon_config
    from .routes import router
except ImportError:
    from config import get_daemon_config
    from routes import router


def create_app() -> FastAPI:
    config = get_daemon_config()

    application = FastAPI(
        title="GMP Simulink Node Daemon",
        version="0.1.0",
        description="Minimal synchronous daemon for remote Simulink execution",
    )
    application.include_router(router)

    @application.get("/")
    def root() -> dict:
        return {
            "name": "gmp-simulink-node-daemon",
            "status": "ok",
            "listen": f"{config.host}:{config.port}",
        }

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn

    cfg = get_daemon_config()
    uvicorn.run("app:app", host=cfg.host, port=cfg.port, reload=False)
