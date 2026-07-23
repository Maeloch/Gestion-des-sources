"""Routes FastAPI."""
from app.routes.sources import router as sources_router
from app.routes.radionuclides import router as radionuclides_router
from app.routes.audit import router as audit_router
from app.routes.auth import router as auth_router
from app.routes.users import router as users_router
from app.routes.consumptions import router as consumptions_router
from app.routes.locations import router as locations_router
from app.routes.movements import router as movements_router
from app.routes.import_export import router as import_export_router
from app.routes.laraweb import router as laraweb_router

__all__ = [
    "sources_router",
    "radionuclides_router",
    "audit_router",
    "auth_router",
    "users_router",
    "consumptions_router",
    "locations_router",
    "movements_router",
    "import_export_router",
    "laraweb_router",
]
