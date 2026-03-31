"""
Authentication module for Snowflake Cortex A2A agents (SPCS runtime).
"""
import os

SPCS_TOKEN_PATH = "/snowflake/session/token"


def get_spcs_session_token() -> str:
    """
    Read the SPCS session token from the standard token file.

    Returns:
        The session token string

    Raises:
        ValueError: If token file is not found or empty
    """
    try:
        with open(SPCS_TOKEN_PATH, "r") as token_file:
            token = token_file.read().strip()
            if not token:
                raise ValueError("SPCS session token file is empty")
            return token
    except FileNotFoundError:
        raise ValueError(
            f"SPCS session token not found at {SPCS_TOKEN_PATH}. "
            "Make sure you are running inside Snowpark Container Services."
        )


def get_auth_token_and_type() -> tuple[str, str]:
    """
    Get the SPCS session token for authentication.

    Returns:
        Tuple of (token, "OAUTH")
    """
    return get_spcs_session_token(), "OAUTH"
