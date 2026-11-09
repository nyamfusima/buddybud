from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Agent, User
from app.db.session import get_db
from app.services import metrics

router = APIRouter(tags=["me"])


def dashboard_bundle(db: Session, agent: Agent, user: User) -> dict:
    """Everything the agent dashboard renders: their data, site settings and the coaching templates."""
    return {
        "data": metrics.agent_payload(db, agent, user.org),
        "shared": metrics.shared_block(db, user.org),
        "coaching": metrics.coaching_kb(db, user.org_id),
    }


@router.get("/me/dashboard")
def my_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.agent_id:
        raise HTTPException(404, "Your account isn't linked to an agent record.")
    agent = db.get(Agent, user.agent_id)
    if not agent or agent.org_id != user.org_id:
        raise HTTPException(404, "Agent record not found.")
    return dashboard_bundle(db, agent, user)


@router.get("/leaderboard")
def get_leaderboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return metrics.leaderboard(db, user.org)
