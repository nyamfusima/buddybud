from collections.abc import Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db.models import Agent, AuditLog, Role, User
from app.db.session import get_db

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if not creds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    from app.core.security import decode_access_token

    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired — please sign in again.") from e
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or user.org_id != payload.get("org"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not active.")
    return user


def require_roles(*roles: Role) -> Callable[[User], User]:
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this.")
        return user

    return _dep


MANAGERS = (Role.tl, Role.om, Role.admin)


def visible_agents_query(user: User) -> Select:
    """The single place that decides which agents a user may see. Every team/insight query goes through it."""
    q = select(Agent).where(Agent.org_id == user.org_id)
    if user.role == Role.admin:
        return q
    if user.role == Role.om:
        return q.where(Agent.om_name == (user.scope_name or "\x00"))
    if user.role == Role.tl:
        return q.where(Agent.tl_name == (user.scope_name or "\x00"))
    return q.where(Agent.id == (user.agent_id or -1))


def get_visible_agent(db: Session, user: User, agent_id: int) -> Agent:
    agent = db.scalars(visible_agents_query(user).where(Agent.id == agent_id)).first()
    if not agent:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Agent not found.")
    return agent


def audit(db: Session, user: User | None, action: str, org_id: int | None = None, **detail) -> None:
    db.add(AuditLog(org_id=org_id or (user.org_id if user else 0), user_id=user.id if user else None,
                    action=action, detail=detail))
