from __future__ import annotations

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.db.base import Base, DB_SCHEMA
from src.db.models import (
    Jobs, Operators, ImportSession, Media, Decisions, Exports, LocalArchives, ExportDeliveries
)

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

def main() -> None:
    engine = create_engine(DATABASE_URL, future= True)

    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {DB_SCHEMA};"))

    with Session(engine) as s:
        # 1) operator + job
        op = Operators(operator_id="op_001", name="Test Operator", role="operator")
        job = Jobs(job_id="job_001", status="open")

        # Upsert-ish behavior for smoke test (avoid rerun crash)
        s.merge(op)
        s.merge(job)
        s.commit()

        # 2) import session
        sess = ImportSession(
            operator_id="op_001",
            job_id="job_001",
            uut_serial="UUT-ABC-123",
            session_purpose="initial",
            status="running",
        )
        s.add(sess)
        s.commit()
        s.refresh(sess)

        # 3) media (2 rows)
        m1 = Media(
            import_session_id=sess.import_session_id,
            adapter="olympuswifi",
            vendor_id="DCIM/100OLYMP/P1000001.JPG",
            local_path=r"C:\IPDS\Incoming\P1000001.JPG",
            size_bytes=123456,
        )
        m2 = Media(
            import_session_id=sess.import_session_id,
            adapter="olympuswifi",
            vendor_id="DCIM/100OLYMP/P1000002.JPG",
            local_path=r"C:\IPDS\Incoming\P1000002.JPG",
            size_bytes=234567,
        )
        s.add_all([m1, m2])
        s.commit()
        s.refresh(m1)
        s.refresh(m2)

        # 4) decisions
        d1 = Decisions(media_id=m1.media_id, status="accepted", reason="OK", notes="sharp")
        d2 = Decisions(media_id=m2.media_id, status="rejected", reason="blur", notes="retake")
        s.add_all([d1, d2])
        s.commit()

        # 5) export
        exp = Exports(
            import_session_id=sess.import_session_id,
            export_path=r"C:\IPDS\Exports\job_001\export_001.zip",
            manifest_path=r"C:\IPDS\Exports\job_001\manifest.json",
            manifest_hash="deadbeef",
            status="created",
        )
        s.add(exp)
        s.commit()
        s.refresh(exp)

        # 6) local archive (mandatory)
        arch = LocalArchives(
            export_id=exp.export_id,
            archive_path=r"C:\IPDS\Archive\job_001\export_001.zip",
            verify_status="verified",
            last_error=None,
        )
        s.add(arch)
        s.commit()

        # 7) export delivery log (operator copy)
        delivery = ExportDeliveries(
            export_id=exp.export_id,
            delivered_by="op_001",
            destination_path=r"C:\Users\USER\Downloads\export_001.zip",
            result="succeeded",
            error_message=None,
        )
        s.add(delivery)
        s.commit()

        print("✅ Smoke test completed OK")
        print("import_session_id =", sess.import_session_id)
        print("export_id =", exp.export_id)


if __name__ == "__main__":
    main()