"""Per-request transaction-scoped PostgreSQL Row-Level Security (RLS) context binding."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession


def _install_session_rls_hook(sync_session: Any) -> None:
    if sync_session.info.get("_rls_hook_installed"):
        return

    @event.listens_for(sync_session, "after_begin")
    def _set_local_user_on_begin(session: Any, _transaction: Any, connection: Any) -> None:
        uid = session.info.get("rls_user_id")
        if uid:
            connection.execute(
                text("SELECT set_config('app.current_user_id', :uid, true)"),
                {"uid": str(uid)},
            )

    sync_session.info["_rls_hook_installed"] = True


async def bind_rls_user_context(db: Any, user_id: uuid.UUID | str) -> None:
    """
    Binds `app.current_user_id` strictly to the current PostgreSQL transaction via
    `set_config(..., is_local=true)` AND automatically re-applies it on any subsequent
    transaction opened within the same request session. Because `is_local=true` clears
    on COMMIT/ROLLBACK, pooled asyncpg connections never bleed identity across requests.
    """
    if not isinstance(db, AsyncSession):
        return
    uid_str = str(user_id)
    db.sync_session.info["rls_user_id"] = uid_str
    _install_session_rls_hook(db.sync_session)
    await db.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": uid_str},
    )
