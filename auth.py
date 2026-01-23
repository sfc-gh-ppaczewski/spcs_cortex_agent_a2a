"""
Authentication module for Snowflake Cortex A2A Agent.
Supports both SPCS session token and Key-Pair JWT authentication.
"""
import os
import time
import base64
import jwt
from cryptography.hazmat.primitives import serialization, hashes

# SPCS token file path (standard location in Snowpark Container Services)
SPCS_TOKEN_PATH = "/snowflake/session/token"


def is_running_in_spcs() -> bool:
    """
    Check if the application is running inside Snowpark Container Services.
    
    Returns:
        True if running in SPCS, False otherwise
    """
    return os.path.exists(SPCS_TOKEN_PATH)


def get_spcs_session_token() -> str:
    """
    Read the SPCS session token from the standard token file.
    
    In SPCS, Snowflake automatically provisions a session token at
    /snowflake/session/token that can be used for authentication.
    
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


def generate_snowflake_jwt(account: str, user: str, private_key_path: str) -> str:
    """
    Generates a secure, short-lived JWT for Snowflake API access.
    
    The JWT issuer includes the public key fingerprint as required by Snowflake.
    
    Args:
        account: Snowflake account locator (e.g., ABC12345)
        user: Snowflake username
        private_key_path: Path to the RSA private key file (.p8)
    
    Returns:
        A signed JWT token string
    
    Raises:
        ValueError: If private key file is not found
    """
    
    # Load Private Key
    try:
        with open(private_key_path, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(), 
                password=None  # Add password here if your key is encrypted
            )
    except FileNotFoundError:
        raise ValueError(f"Private Key not found at {private_key_path}")

    # Compute public key fingerprint (SHA256)
    public_key = private_key.public_key()
    public_key_der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    digest = hashes.Hash(hashes.SHA256())
    digest.update(public_key_der)
    fingerprint = base64.b64encode(digest.finalize()).decode('utf-8')

    # Generate JWT claims
    # Use uppercase for Account/User to avoid common 403 errors
    qualified_name = f"{account.upper()}.{user.upper()}"
    
    # Snowflake requires the fingerprint in the issuer claim
    issuer_with_fingerprint = f"{qualified_name}.SHA256:{fingerprint}"
    
    payload = {
        "iss": issuer_with_fingerprint,
        "sub": qualified_name,
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600  # 1 hour expiration
    }
    
    # Sign Token
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token


def get_auth_token_and_type() -> tuple[str, str]:
    """
    Get the appropriate authentication token based on the environment.
    
    When running in SPCS, uses the session token.
    When running locally, uses JWT key-pair authentication.
    
    Returns:
        Tuple of (token, token_type) where token_type is either
        'OAUTH' for SPCS or 'KEYPAIR_JWT' for local
    
    Raises:
        ValueError: If authentication cannot be established
    """
    if is_running_in_spcs():
        token = get_spcs_session_token()
        return token, "OAUTH"
    else:
        # Fall back to JWT key-pair auth for local development
        account_locator = os.getenv("SNOWFLAKE_ACCOUNT_LOCATOR")
        user = os.getenv("SNOWFLAKE_USER")
        key_path = os.getenv("PRIVATE_KEY_PATH")
        
        if not all([account_locator, user, key_path]):
            raise ValueError(
                "For local development, SNOWFLAKE_ACCOUNT_LOCATOR, "
                "SNOWFLAKE_USER, and PRIVATE_KEY_PATH must be set"
            )
        
        token = generate_snowflake_jwt(account_locator, user, key_path)
        return token, "KEYPAIR_JWT"
