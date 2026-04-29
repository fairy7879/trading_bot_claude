from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    twelvedata_api_key: str = Field(default="", description="Twelve Data API key.")

    ostium_private_key: str = Field(default="", description="EVM private key for Ostium.")
    ostium_rpc_url: str = Field(default="", description="Arbitrum RPC URL.")
    ostium_network: Literal["sepolia", "arbitrum"] = Field(default="sepolia")
    ostium_allow_mainnet: bool = Field(default=False)

    data_cache_dir: Path = Field(default=Path(".cache/trading_bot"))


def get_settings() -> Settings:
    return Settings()
