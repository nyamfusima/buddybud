"""Admin CLI.  Run from backend/:  python -m app.cli <command>

  init-db                         create tables (dev/sqlite; use `alembic upgrade head` for Postgres in prod)
  seed-demo                       create the synthetic "Demo Contact Centre" with ~200 agents and 13 months of surveys
  create-org NAME SLUG LABEL      new tenant (copies the default coaching playbook)
  create-admin SLUG EMAIL NAME    admin user for a tenant (prints a temporary password)
  classify [SLUG]                 classify unlabelled detractor comments
  attrition [SLUG]                train + score the attrition early-warning model
"""

import secrets
import sys

from sqlalchemy import select

from app.db import models  # noqa: F401  (register tables)
from app.db.models import Organization, Role, User
from app.db.session import Base, SessionLocal, engine


def _org(db, slug: str) -> Organization:
    org = db.scalars(select(Organization).where(Organization.slug == slug)).first()
    if not org:
        sys.exit(f"No organisation with slug '{slug}'.")
    return org


def main(argv: list[str]) -> None:
    if not argv:
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]
    if cmd == "init-db":
        Base.metadata.create_all(engine)
        print("Tables created.")
        return
    with SessionLocal() as db:
        if cmd == "seed-demo":
            Base.metadata.create_all(engine)
            from app.seed.demo import generate_demo

            res = generate_demo(db)
            print("Demo data ready:", res)
            from app.ml import attrition
            from app.pipelines.classify import classify_pending

            org = _org(db, "demo")
            print("classifier:", classify_pending(db, org.id))
            print("attrition train:", attrition.train(db, org.id))
            print("attrition score:", attrition.score(db, org.id))
        elif cmd == "create-org":
            from app.seed.demo import create_org

            name, slug, label = args[0], args[1], (args[2] if len(args) > 2 else "Customer Care")
            create_org(db, name, slug, label)
            db.commit()
            print(f"Created organisation {slug}.")
        elif cmd == "create-admin":
            from app.core.security import hash_password

            org = _org(db, args[0])
            temp = secrets.token_urlsafe(9) + "A1"
            db.add(User(org_id=org.id, email=args[1].lower(), full_name=args[2], role=Role.admin,
                        password_hash=hash_password(temp), must_change_password=True))
            db.commit()
            print(f"Admin {args[1]} created. Temporary password: {temp}")
        elif cmd == "classify":
            from app.pipelines.classify import classify_pending

            for org in ([_org(db, args[0])] if args else db.scalars(select(Organization))):
                print(org.slug, classify_pending(db, org.id))
        elif cmd == "attrition":
            from app.ml import attrition

            for org in ([_org(db, args[0])] if args else db.scalars(select(Organization))):
                print(org.slug, attrition.train(db, org.id), attrition.score(db, org.id))
        else:
            print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
