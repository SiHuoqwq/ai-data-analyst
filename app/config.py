import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_provider: str = "deepseek"
    database_url: str = "sqlite:///./app.db"
    upload_dir: str = "./storage/uploads"
    chart_dir: str = "./storage/charts"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
os.makedirs(settings.upload_dir, exist_ok=True)
os.makedirs(settings.chart_dir, exist_ok=True)
