from __future__ import annotations

import json

from app.db.session import SessionLocal
from app.services.operations.cleanup_service import OperationalCleanupService


def main() -> None:
    session = SessionLocal()
    try:
        result = OperationalCleanupService(session).cleanup_operational_data()
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        session.close()


if __name__ == "__main__":
    main()
