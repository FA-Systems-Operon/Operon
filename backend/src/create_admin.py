"""Create the first admin. Sign-up is invite-only, so someone has to exist to invite people.

Run inside the api container:

    docker compose exec api python -m src.create_admin you@example.com "Your Name"

It asks for the password. For scripts, set OPERON_ADMIN_PASSWORD instead.
"""

import argparse
import getpass
import os

import src.models  # noqa: F401  (importing registers every table)
from src.auth import AuthError, create_user
from src.db import Base, SessionLocal, engine
from src.models import Role


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("email")
    parser.add_argument("display_name")
    args = parser.parse_args()

    password = os.environ.get("OPERON_ADMIN_PASSWORD") or getpass.getpass("Password: ")

    Base.metadata.create_all(bind=engine)  # make sure the tables exist
    with SessionLocal() as db:
        try:
            user = create_user(db, args.email, args.display_name, password, Role.ADMIN)
        except AuthError as error:
            raise SystemExit(f"Could not create the admin: {error}")
    print(f"Created admin {user.email}")


if __name__ == "__main__":
    main()
