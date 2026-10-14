"""Create a doctor account. Doctors can never self-register through the API (they can read every patient).

    python -m scripts.create_doctor --email dr.rao@clinic.org --name "Dr. A. Rao"
Password is prompted (or taken from env DOCTOR_PASSWORD for automation). Min 10 characters.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from sqlalchemy.orm import sessionmaker

from app import db_models  # noqa: F401
from app.core.config import get_settings
from app.core.database import Base, make_engine
from app.modules.auth import service
from app.modules.auth.models import Role


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", required=True)
    args = ap.parse_args()

    pw = os.environ.get("DOCTOR_PASSWORD")
    if not pw:
        pw = getpass.getpass("Password: ")
        if pw != getpass.getpass("Repeat password: "):
            print("Passwords do not match", file=sys.stderr)
            return 1
    if len(pw) < 10:
        print("Password must be at least 10 characters", file=sys.stderr)
        return 1

    engine = make_engine(get_settings().database_url)
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        if service.get_user_by_email(db, args.email):
            print("A user with that email already exists", file=sys.stderr)
            return 1
        user = service.create_user(db, email=args.email, password=pw, full_name=args.name, role=Role.DOCTOR)
        db.commit()
        print(f"Created doctor {user.email} (id {user.id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
