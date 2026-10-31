from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that are fine on a laptop but must never run in production.
_PLACEHOLDER_SECRETS = {"change-me", "change-this-to-a-long-random-string"}


class Settings(BaseSettings):
    """App settings, read from environment variables or a .env file."""

    database_url: str = "postgresql+psycopg2://clinic:clinic@localhost:5432/clinicslot"
    secret_key: str = "change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # "development" (default) or "production". Production refuses to start with a weak SECRET_KEY.
    environment: str = "development"
    # Doctors' working hours are wall-clock times in this timezone.
    clinic_timezone: str = "Asia/Kolkata"
    # Patients cannot cancel or reschedule an appointment that starts sooner than this.
    cancellation_cutoff_hours: int = 2

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def use_psycopg2_driver(cls, value: str) -> str:
        """Hosts hand out postgres:// or postgresql:// URLs; SQLAlchemy 2 needs the driver named."""
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg2://" + value[len(prefix):]
        return value

    def assert_production_ready(self) -> None:
        """Called at startup. Fail loudly instead of running with a guessable signing key."""
        if self.environment.lower() != "production":
            return
        if self.secret_key in _PLACEHOLDER_SECRETS or len(self.secret_key) < 32:
            raise RuntimeError(
                "SECRET_KEY must be a long random value (at least 32 characters) "
                "when ENVIRONMENT=production"
            )


settings = Settings()
