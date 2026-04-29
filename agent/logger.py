import logging
import os
from typing import Optional


LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_configured = False


def _coerce_level(level: Optional[str | int]) -> int:
	if isinstance(level, int):
		return level
	if isinstance(level, str):
		try:
			# TODO: fix depricated function
			return logging.getLevelName(level.upper())  # type: ignore[arg-type]
		except Exception:
			return logging.INFO
	return logging.INFO


def configure_logging(level: Optional[str | int] = None) -> None:
	"""Configure the root logger once for the entire application."""

	global _configured

	resolved_level = _coerce_level(level or os.getenv("AGENT_LOG_LEVEL", "INFO"))

	root_logger = logging.getLogger()
	root_logger.setLevel(resolved_level)

	if _configured:
		return

	handler = logging.StreamHandler()
	handler.setFormatter(logging.Formatter(LOG_FORMAT))

	root_logger.handlers.clear()
	root_logger.addHandler(handler)

	# Ensure uvicorn logs integrate with our configuration
	logging.getLogger("uvicorn").handlers.clear()
	logging.getLogger("uvicorn.access").handlers.clear()
	logging.getLogger("uvicorn.error").handlers.clear()

	_configured = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
	"""Return a module-scoped logger, configuring the system if needed."""

	configure_logging()
	return logging.getLogger(name or "agent")