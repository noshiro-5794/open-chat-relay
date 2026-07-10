from fastapi import APIRouter

from app.api.v1.routes.app_api import router as app_api_router
from app.api.v1.routes.apps import app_router
from app.api.v1.routes.apps import workspace_router as apps_workspace_router
from app.api.v1.routes.attachments import router as attachments_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.capabilities import router as capabilities_router
from app.api.v1.routes.internal_gateway import router as internal_gateway_router
from app.api.v1.routes.me import router as me_router
from app.api.v1.routes.messages import router as messages_router
from app.api.v1.routes.notifications import router as notifications_router
from app.api.v1.routes.presence import router as presence_router
from app.api.v1.routes.reactions import router as reactions_router
from app.api.v1.routes.read_states import router as read_states_router
from app.api.v1.routes.realtime import router as realtime_router
from app.api.v1.routes.rooms import room_router, workspace_router
from app.api.v1.routes.sse import router as sse_router
from app.api.v1.routes.system import router as system_router
from app.api.v1.routes.typing import router as typing_router
from app.api.v1.routes.users import router as users_router
from app.api.v1.routes.webhooks import router as webhooks_router
from app.api.v1.routes.workspaces import router as workspaces_router

api_router = APIRouter()
api_router.include_router(app_api_router)
api_router.include_router(apps_workspace_router)
api_router.include_router(app_router)
api_router.include_router(attachments_router)
api_router.include_router(auth_router)
api_router.include_router(capabilities_router, tags=["capabilities"])
api_router.include_router(internal_gateway_router)
api_router.include_router(me_router)
api_router.include_router(messages_router)
api_router.include_router(notifications_router)
api_router.include_router(presence_router)
api_router.include_router(read_states_router)
api_router.include_router(realtime_router)
api_router.include_router(reactions_router)
api_router.include_router(sse_router)
api_router.include_router(system_router)
api_router.include_router(typing_router)
api_router.include_router(users_router)
api_router.include_router(webhooks_router)
api_router.include_router(workspaces_router)
api_router.include_router(workspace_router)
api_router.include_router(room_router)
