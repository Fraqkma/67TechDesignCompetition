"""Enlightenment Compass Flask application entry point.

The application factory intentionally stays small. Configuration, database
pooling, shared operations, and route groups live in focused ``backend``
modules so contributors can understand or test one area at a time.

Public imports such as ``app``, ``create_app``, ``get_db``, ``AIService``, and
``TeachingAssistant`` remain here for backwards compatibility with launchers,
scripts, and existing tests.
"""

from __future__ import annotations

from flask import Flask

from backend import (
    AIAnalyzer,
    AIService,
    GraphEngine,
    GraphValidationError,
    PlanService,
    TeachingAssistant,
)
from backend.application_services import ApplicationServices
from backend.config import configure_flask_app
from backend.database import get_db
from backend.routes.account import register_account_routes
from backend.routes.ai import register_ai_routes
from backend.routes.learning import register_learning_routes
from backend.routes.pages import register_page_routes
from backend.routes.responses import register_response_compression
from backend.study_buddy_routes import create_study_buddy_blueprint


__all__ = [
    "AIAnalyzer",
    "AIService",
    "GraphEngine",
    "GraphValidationError",
    "PlanService",
    "TeachingAssistant",
    "app",
    "create_app",
    "get_db",
]


def create_app(database_path: str | None = None) -> Flask:
    """Build and configure one Flask application instance.

    ``database_path`` is accepted for compatibility with the original JSON
    prototype. The current application loads graph data from PostgreSQL.
    """

    # Keep Flask rooted at this module so the existing templates/ and static/
    # directories continue to resolve without custom path configuration.
    app = Flask(__name__)
    configure_flask_app(app)
    register_response_compression(app)

    services = ApplicationServices(get_db, AIService)
    # Exposing services through Flask's extension registry makes dependency
    # replacement straightforward in future isolated route tests.
    app.extensions["enlightenment_compass"] = services

    register_page_routes(app, services)
    register_account_routes(app, services)
    register_learning_routes(app, services, PlanService)
    register_ai_routes(app, services, AIAnalyzer, TeachingAssistant)
    app.register_blueprint(create_study_buddy_blueprint(get_db))
    return app


# WSGI servers import this object. Database connections are still lazy and are
# created only when the first database-backed request arrives.
app = create_app()


if __name__ == "__main__":
    from waitress import serve

    serve(app, host="127.0.0.1", port=5000, threads=8)
