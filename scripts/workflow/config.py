from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field, Field

class Config(BaseSettings):
    LITELLM_HOST: str = Field(default="https://api.openai.com/v1")
    LITELLM_API_KEY: str
    PROXY_USERNAME: str
    PROXY_PASSWORD: str
    PROXY_HOST: str
    PROXY_PORT: int
    
    @computed_field
    @property
    def PROXY_STRING(self) -> str:
        return f"http://{self.PROXY_USERNAME}:{self.PROXY_PASSWORD}@{self.PROXY_HOST}:{self.PROXY_PORT}/"

config = Config()
