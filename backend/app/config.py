from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str = "http://localhost:8000/auth/callback"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    session_secret: str  # Fernet key
    frontend_origin: str = "http://localhost:5173"
    cookie_secure: bool = False

    scopes: list[str] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    ]


settings = Settings()
