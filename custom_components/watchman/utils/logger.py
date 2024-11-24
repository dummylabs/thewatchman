"""Custom logger for HACS."""

import logging

from ..const import PACKAGE_NAME

_LOGGER: logging.Logger = logging.getLogger(PACKAGE_NAME)
INDENT = "  "
