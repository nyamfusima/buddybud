from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agents.coach import service
from app.api.deps import get_current_user
from app.core.llm import provider_info
from app.db.models import ChatMessage, User
from app.db.session import SessionLocal, get_db

router = APIRouter(prefix="/coach", tags=["coach"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.post("/chat")
async def chat(body: ChatIn, user: User = Depends(get_current_user)):
    if not user.agent_id:
        raise HTTPException(400, "The coach chat is for agent accounts.")
    if service.rate_limited(user.id):
        raise HTTPException(429, "You've sent a lot of messages in a short time — give it a few minutes.")
    user_id, org_id = user.id, user.org_id

    def _prepare():
        with SessionLocal() as db:
            u = db.get(User, user_id)
            return service.prepare(db, u, body.message.strip())

    ctx = await run_in_threadpool(_prepare)

    def save(text: str, label: str | None):
        with SessionLocal() as db:
            db.add(ChatMessage(org_id=org_id, user_id=user_id, role="assistant", content=text, safety_label=label))
            if label == "crisis":
                # flag the user's message too so it can be followed up under the org's welfare policy
                last = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user_id, ChatMessage.role == "user")
                                  .order_by(ChatMessage.id.desc())).first()
                if last:
                    last.safety_label = "crisis"
            db.commit()

    return StreamingResponse(service.stream_reply(ctx, body.message.strip(), save), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/history")
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ChatMessage).where(ChatMessage.user_id == user.id).order_by(ChatMessage.id)).all()
    return {"messages": [{"role": r.role, "content": r.content, "at": r.created_at.isoformat() if r.created_at else None}
                         for r in rows[-50:]], **provider_info()}


@router.delete("/history")
def clear_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    db.commit()
    return {"ok": True}
