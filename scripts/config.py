"""
Config loader for Public.com skill.
Reads API secret and account ID from environment variables.
"""
import os


def get_api_secret():
    """
    Get PUBLIC_COM_SECRET from environment.
    Returns the secret string or None if not found.
    """
    return os.getenv("PUBLIC_COM_SECRET")


def get_account_id():
    """
    Get PUBLIC_COM_ACCOUNT_ID from environment.
    Returns the account ID string or None if not found.
    """
    return os.getenv("PUBLIC_COM_ACCOUNT_ID")
