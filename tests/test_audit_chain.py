from sqlalchemy import delete, update

from src.models import AuditLog


def _events(app, count=3):
    from src.audit_logger import log_action
    with app.app_context():
        return [log_action(None, f"EVENT_{index}", "test", {"index": index}) for index in range(count)]


def test_valid_audit_chain(app):
    _events(app)
    from src.audit_logger import verify_integrity
    with app.app_context():
        valid, errors = verify_integrity()
    assert valid is True
    assert errors == []


def test_modified_audit_entry_is_detected(app):
    rows = _events(app)
    from src.db import serialized_session
    with serialized_session() as session:
        session.execute(update(AuditLog).where(AuditLog.id == rows[1].id).values(action="ALTERED"))
    from src.audit_logger import verify_integrity_detailed
    with app.app_context():
        result = verify_integrity_detailed()
    assert result["valid"] is False
    assert any(code in {"invalid_hash", "invalid_hmac"} for _row, code in result["errors"])


def test_missing_middle_entry_is_detected(app):
    rows = _events(app)
    from src.db import serialized_session
    with serialized_session() as session:
        session.execute(delete(AuditLog).where(AuditLog.id == rows[1].id))
    from src.audit_logger import verify_integrity_detailed
    with app.app_context():
        result = verify_integrity_detailed()
    assert result["valid"] is False
    assert any(code == "missing_sequence" for _row, code in result["errors"])


def test_tail_deletion_limitation_is_reported(app):
    rows = _events(app)
    from src.db import serialized_session
    with serialized_session() as session:
        session.execute(delete(AuditLog).where(AuditLog.id == rows[-1].id))
    from src.audit_logger import verify_integrity_detailed
    with app.app_context():
        result = verify_integrity_detailed()
    assert result["valid"] is True
    assert any("Tail truncation" in text for text in result["limitations"])


def test_audit_events_have_unique_sequence_and_event_id(app):
    _events(app, 5)
    from src.db import session_factory
    session = session_factory()
    try:
        rows = session.query(AuditLog).all()
        assert len({row.sequence for row in rows}) == 5
        assert len({row.event_id for row in rows}) == 5
    finally:
        session.close()

