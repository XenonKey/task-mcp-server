from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    aws_region: str
    cognito_user_pool_id: str
    cognito_app_client_id: str
    mcp_resource_server_url: str
    task_api_base: str

    model_config = SettingsConfigDict(env_file=Path(__file__).parent / ".env", extra="ignore")


settings = Settings()
