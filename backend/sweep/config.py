"""Settings. Only the Google client ID and secret are required; everything
else has a default that works for a single local process on 127.0.0.1."""
from cryptography.fernet import Fernet
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PORT = 8000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    google_client_id: str
    google_client_secret: str
    port: int = DEFAULT_PORT
    # Google's OAuth "Desktop app" client type accepts any loopback URI, so
    # this needs no registration. A "Web application" client must list it.
    google_redirect_uri: str = ""

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Fernet key for the session cookie. Generated fresh at startup when
    # unset: on a laptop, "restart the server == sign in again" is fine.
    session_secret: str = Field(default_factory=lambda: Fernet.generate_key().decode())

    # Only set when the Vite dev server is running the UI. Left empty, the
    # backend serves the built frontend itself and redirects to "/".
    frontend_origin: str = ""
    cookie_secure: bool = False

    scopes: list[str] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    ]

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def redirect_uri(self) -> str:
        return self.google_redirect_uri or f"{self.base_url}/auth/callback"

    @property
    def after_login_url(self) -> str:
        return self.frontend_origin or "/"


settings = Settings()
