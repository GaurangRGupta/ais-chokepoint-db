from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Secrets and connection strings. Loaded from the process env or `.env`."""

    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    aisstream_api_key: str = Field(default="", alias="AISSTREAM_API_KEY")
    openwaters_api_key: str = Field(default="", alias="OPENWATERS_API_KEY")
    database_url: str = Field(default="", alias="DATABASE_URL")
    azure_storage_account: str = Field(default="", alias="AZURE_STORAGE_ACCOUNT")
    azure_blob_container: str = Field(default="ais-raw", alias="AZURE_BLOB_CONTAINER")
    azure_storage_connection_string: str = Field(
        default="", alias="AZURE_STORAGE_CONNECTION_STRING"
    )
    azure_storage_key: str = Field(default="", alias="AZURE_STORAGE_KEY")

    @field_validator(
        "aisstream_api_key",
        "openwaters_api_key",
        "database_url",
        "azure_storage_account",
        "azure_blob_container",
        "azure_storage_connection_string",
        "azure_storage_key",
        mode="before",
    )
    @classmethod
    def strip_optional(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    def require_aisstream_key(self) -> str:
        if not self.aisstream_api_key:
            raise SystemExit(
                "AISSTREAM_API_KEY is empty. Put it in adbms_project/.env and do not commit that file."
            )
        return self.aisstream_api_key

    def require_openwaters_key(self) -> str:
        if not self.openwaters_api_key:
            raise SystemExit(
                "OPENWATERS_API_KEY is empty. Put the Open Waters token in adbms_project/.env."
            )
        return self.openwaters_api_key

    def require_database_url(self) -> str:
        if not self.database_url:
            raise SystemExit(
                "DATABASE_URL is empty. Put the PostgreSQL URL in adbms_project/.env "
                "with sslmode=require. Do not commit that file."
            )
        return self.database_url

    def require_blob_auth(self) -> None:
        if self.azure_storage_connection_string:
            return
        if self.azure_storage_account and self.azure_storage_key:
            return
        raise SystemExit(
            "Blob auth is empty. Set AZURE_STORAGE_CONNECTION_STRING, or "
            "AZURE_STORAGE_ACCOUNT plus AZURE_STORAGE_KEY, in adbms_project/.env."
        )
