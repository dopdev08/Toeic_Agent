import os
import pytest

# Default tests to an isolated SQLite database to protect toeic_agent.db
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_runner.db")


@pytest.fixture(scope="session", autouse=True)
def verify_test_db_isolation():
    """Verify engine is bound to an isolated test database and never toeic_agent.db."""
    from app.db.database import engine
    engine_url_str = str(engine.url)
    assert "test_runner.db" in engine_url_str or ":memory:" in engine_url_str, (
        f"CRITICAL SAFETY VIOLATION: Tests are not isolated! Engine URL bound to: {engine_url_str}"
    )
    assert "toeic_agent.db" not in engine_url_str, (
        f"CRITICAL SAFETY VIOLATION: Engine URL is bound to production database: {engine_url_str}"
    )
