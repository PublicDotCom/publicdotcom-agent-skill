"""
Config loader for Public.com skill.
Reads API secret and account ID from environment variables.
"""
import os
import subprocess
import sys


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


def create_client(secret, account_id=None):
    """
    Create a PublicApiClient with a custom User-Agent for observability.
    Installs the SDK if not already present.
    """
    try:
        from public_api_sdk import PublicApiClient, PublicApiClientConfiguration
        from public_api_sdk.auth_config import ApiKeyAuthConfig
    except ImportError:
        print("Installing required dependency: publicdotcom-py...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "publicdotcom-py==0.1.15"])
        from public_api_sdk import PublicApiClient, PublicApiClientConfiguration
        from public_api_sdk.auth_config import ApiKeyAuthConfig

    client = PublicApiClient(
        ApiKeyAuthConfig(api_secret_key=secret),
        config=PublicApiClientConfiguration(default_account_number=account_id),
    )
    client.api_client.session.headers["User-Agent"] = "agent-skill/1.0"
    return client
