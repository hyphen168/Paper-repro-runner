import logging
from pathlib import Path


def setup_logging(log_file='app.log', level=logging.INFO):
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_file,
        filemode='a',
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=level,
    )
    return logging.getLogger(__name__)


def log_info(message):
    logging.getLogger(__name__).info(message)


def log_warning(message):
    logging.getLogger(__name__).warning(message)


def log_error(message):
    logging.getLogger(__name__).error(message)


def log_debug(message):
    logging.getLogger(__name__).debug(message)
