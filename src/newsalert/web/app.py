from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.engine import Engine
from starlette.middleware.sessions import SessionMiddleware

from newsalert.db.session import make_engine
from newsalert.delivery.channels import ChannelSender
from newsalert.delivery.config import DeliverySettings
from newsalert.settings import Settings
from newsalert.web.admin import format_timestamp
from newsalert.web.admin import router as admin_router
from newsalert.web.routes import router

HERE = Path(__file__).parent


def create_app(
    settings: Settings | None = None, engine: Engine | None = None, sender=None
) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="News alerts")
    app.state.engine = engine if engine is not None else make_engine(settings.database_url)
    app.state.templates = Jinja2Templates(directory=HERE / "templates")
    app.state.templates.env.filters["ts"] = format_timestamp
    app.state.admin_emails = settings.admin_email_set()
    app.state.sender = sender if sender is not None else ChannelSender(DeliverySettings())
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        session_cookie="newsalert_session",
        same_site="lax",
        https_only=settings.cookie_secure,
        max_age=settings.session_seconds,
    )

    @app.middleware("http")
    async def private_responses(request: Request, call_next):
        response = await call_next(request)
        if not request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self'; script-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, error):
        # FastAPI's default response includes submitted values, including passwords/webhooks.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
                    for item in error.errors()
                ]
            },
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.include_router(router)
    app.include_router(admin_router)
    # Schema creation and migrations deliberately belong to the joint integration step.
    return app
