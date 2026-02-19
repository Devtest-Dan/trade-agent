"""Entry point — starts the Trade Agent."""

import sys
from pathlib import Path

import uvicorn
from loguru import logger

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.config import settings


def main():
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level="INFO",
    )
    logger.add(
        "data/trade_agent.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
    )

    logger.info("=" * 60)
    logger.info("  Trade Agent — AI-Powered MT5 Trading System")
    logger.info("=" * 60)
    logger.info(f"API: http://{settings.api_host}:{settings.api_port}")
    logger.info(f"MT5: {settings.zmq_rep_address} (REP) / {settings.zmq_pub_address} (PUB)")

    from agent.api.main import create_app

    app = create_app()
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
