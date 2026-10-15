from src.config import Settings


def test_settings_read_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("DEBUG", "false")
    settings = Settings()
    assert settings.DATABASE_URL == "sqlite+pysqlite:///:memory:"
    assert settings.DEBUG is False
