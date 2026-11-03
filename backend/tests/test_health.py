import sqlite3

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_reports_database_connection(tmp_path) -> None:
    database_path = tmp_path / "test.db"
    app = create_app(
        Settings(
            database_url=f"sqlite:///{database_path.as_posix()}",
            frontend_origin="http://localhost:3000",
        )
    )

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
    assert database_path.exists()
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert {"companies", "instruments", "alembic_version"}.issubset(tables)

