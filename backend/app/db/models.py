"""Database schema. Every business table carries org_id: one deployment can serve many call centres."""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Role(enum.StrEnum):
    agent = "agent"
    tl = "tl"  # team leader: sees agents whose tl_name == user.scope_name
    om = "om"  # operations manager: sees agents whose om_name == user.scope_name
    admin = "admin"  # sees the whole organisation, runs imports, manages users


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    client_label: Mapped[str] = mapped_column(String(200), default="Customer Care")  # e.g. "Tesco Care (Tesco Mobile)"
    nps_target: Mapped[float] = mapped_column(Float, default=40)
    osat_target: Mapped[float] = mapped_column(Float, default=65)
    thumb_ratio: Mapped[float] = mapped_column(Float, default=3)
    leaderboard_min_n: Mapped[int] = mapped_column(Integer, default=5)
    leaderboard_size: Mapped[int] = mapped_column(Integer, default=10)
    support_contact: Mapped[str] = mapped_column(
        Text,
        default="your Team Leader's manager, HR, or your Employee Assistance Programme (EAP) line",
    )
    crisis_resources: Mapped[str] = mapped_column(
        Text,
        default=("If you're in immediate danger or thinking about harming yourself, contact your local emergency number now "
                 "(South Africa: 112 from a mobile, or the SADAG crisis line 0800 567 567; UK: 999, or Samaritans on 116 123)."),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=10), default=Role.agent)
    scope_name: Mapped[str | None] = mapped_column(String(200))  # TL name or OM name this user manages
    agent_id: Mapped[int | None] = mapped_column(ForeignKey("agents.id", ondelete="SET NULL"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    org: Mapped[Organization] = relationship()
    agent: Mapped[Agent | None] = relationship()


class Agent(Base):
    __tablename__ = "agents"
    __table_args__ = (UniqueConstraint("org_id", "employee_ref"), Index("ix_agents_org_tl", "org_id", "tl_name"))

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    employee_ref: Mapped[str] = mapped_column(String(80))
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    tl_name: Mapped[str] = mapped_column(String(200), default="")
    om_name: Mapped[str] = mapped_column(String(200), default="")
    start_date: Mapped[date | None] = mapped_column(Date)  # employment / training start
    go_live_date: Mapped[date | None] = mapped_column(Date)  # first day taking live calls (tenure is measured from here)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | left
    leave_date: Mapped[date | None] = mapped_column(Date)
    leave_type: Mapped[str | None] = mapped_column(String(20))  # voluntary | involuntary
    leave_reason: Mapped[str | None] = mapped_column(String(200))


class Survey(Base):
    __tablename__ = "surveys"
    __table_args__ = (UniqueConstraint("org_id", "sid"), Index("ix_surveys_org_agent_date", "org_id", "agent_id", "date"))

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    sid: Mapped[str] = mapped_column(String(80))
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, index=True)
    nps: Mapped[int | None] = mapped_column(Integer)
    osat: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(Text, default="")
    vulnerable: Mapped[bool] = mapped_column(Boolean, default=False)

    classification: Mapped[Classification | None] = relationship(
        back_populates="survey", uselist=False, cascade="all, delete-orphan"
    )


class Classification(Base):
    """People/Process classification for a detractor survey (NPS 0-6)."""

    __tablename__ = "classifications"

    survey_id: Mapped[int] = mapped_column(ForeignKey("surveys.id", ondelete="CASCADE"), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(20))  # People | Process | None
    category: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(20), default="import")  # import | llm | keyword | manual
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    survey: Mapped[Survey] = relationship(back_populates="classification")


class CoachingTemplate(Base):
    __tablename__ = "coaching_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    bucket: Mapped[str] = mapped_column(String(20))  # People | Process | DefaultProcess | Closer
    category: Mapped[str] = mapped_column(String(80))
    variant: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(12))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    safety_label: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AttritionScore(Base):
    __tablename__ = "attrition_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id", ondelete="CASCADE"), index=True)
    scored_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    risk: Mapped[float] = mapped_column(Float)
    band: Mapped[str] = mapped_column(String(10))  # low | medium | high
    drivers: Mapped[list] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(20), default="model")  # model | heuristic


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # agents | surveys
    filename: Mapped[str] = mapped_column(String(255))
    rows_ok: Mapped[int] = mapped_column(Integer, default=0)
    rows_bad: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token_hash: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
