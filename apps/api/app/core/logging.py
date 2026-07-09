import logging
from logging.config import dictConfig

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {"format": ("%(asctime)s %(levelname)s [%(name)s] %(message)s")}
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {
                "level": settings.log_level,
                "handlers": ["console"],
            },
        }
    )
    logging.getLogger("uvicorn.access").setLevel(settings.log_level)
