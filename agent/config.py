from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Claude API
    anthropic_api_key: str = ""

    # MT5 ZeroMQ
    mt5_zmq_host: str = "127.0.0.1"
    mt5_zmq_rep_port: int = 5555
    mt5_zmq_pub_port: int = 5556

    # Web server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Auth
    jwt_secret: str = "change-this-to-a-random-secret"
    jwt_expiry_hours: int = 168  # 7 days

    # Telegram (optional)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Database
    db_path: str = "data/trade_agent.db"
    db_cache_mb: int = 64
    upload_max_mb: int = 500
    bar_retention_days: int = 0  # 0 = keep forever

    # Playbooks
    playbooks_dir: str = "data/playbooks"

    # Risk defaults
    default_max_lot: float = 0.1
    default_max_daily_trades: int = 10
    default_max_drawdown_pct: float = 5.0
    default_max_open_positions: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def zmq_rep_address(self) -> str:
        return f"tcp://{self.mt5_zmq_host}:{self.mt5_zmq_rep_port}"

    @property
    def zmq_pub_address(self) -> str:
        return f"tcp://{self.mt5_zmq_host}:{self.mt5_zmq_pub_port}"


settings = Settings()
