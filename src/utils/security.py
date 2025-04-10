import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def validate_user_id(user_id: int, allowed_user_id: int) -> bool:
    """
    Validate that the user ID is authorized.

    Args:
        user_id: User ID to validate
        allowed_user_id: Allowed user ID

    Returns:
        bool: True if user is authorized, False otherwise
    """
    is_valid = user_id == allowed_user_id
    if not is_valid:
        logger.warning(f"Unauthorized access attempt from user ID: {user_id}")

    return is_valid
