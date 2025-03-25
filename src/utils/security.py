import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def validate_transaction_amount(amount: float, max_limit: float) -> None:
    """
    Validate that transaction amount does not exceed the maximum limit.

    Args:
        amount: Transaction amount
        max_limit: Maximum allowed limit

    Raises:
        ValueError: If amount exceeds the maximum limit
    """
    if amount <= 0:
        raise ValueError(f"Transaction amount must be positive, got {amount}")

    if amount > max_limit:
        raise ValueError(
            f"Transaction amount {amount} exceeds maximum limit {max_limit}"
        )

    logger.info(f"Validated transaction amount: {amount} (max: {max_limit})")


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
