"""
Config loader for Public.com skill.
Reads API secret and account ID from environment variables, and owns the single
pinned publicdotcom-py SDK version that every script installs against.
"""
import os
import subprocess
import sys

# The one place the SDK pin lives. requirements.txt and README.md mirror it.
SDK_PACKAGE = "publicdotcom-py"
SDK_VERSION = "0.1.23"

# Skill version. Mirrored in the SKILL.md frontmatter (`metadata.version`).
SKILL_VERSION = "1.1"
USER_AGENT = f"agent-skill/{SKILL_VERSION}"


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


def _version_tuple(version):
    """Turn '0.1.23' (or '0.1.23rc1') into a comparable tuple of ints."""
    parts = []
    for piece in version.split("."):
        digits = ""
        for ch in piece:
            if not ch.isdigit():
                break
            digits += ch
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def ensure_sdk():
    """
    Make sure publicdotcom-py is importable at the pinned version or newer.

    Installs the pinned version when the SDK is missing or older than the pin
    (an older install would lack the endpoints the newer scripts call). A newer
    install is left alone. Call this before any `from public_api_sdk import ...`.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        installed = version(SDK_PACKAGE)
    except PackageNotFoundError:
        installed = None

    if installed is not None and _version_tuple(installed) >= _version_tuple(SDK_VERSION):
        return

    if installed is None:
        print(f"Installing required dependency: {SDK_PACKAGE}=={SDK_VERSION}...")
    else:
        print(f"Upgrading {SDK_PACKAGE} {installed} -> {SDK_VERSION} (required by this skill)...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", f"{SDK_PACKAGE}=={SDK_VERSION}"]
    )


def create_client(secret, account_id=None):
    """
    Create a PublicApiClient with a custom User-Agent for observability.
    Installs (or upgrades) the SDK if the pinned version is not already present.
    """
    ensure_sdk()
    from public_api_sdk import PublicApiClient, PublicApiClientConfiguration
    from public_api_sdk.auth_config import ApiKeyAuthConfig

    client = PublicApiClient(
        ApiKeyAuthConfig(api_secret_key=secret),
        config=PublicApiClientConfiguration(default_account_number=account_id),
    )
    client.api_client.session.headers["User-Agent"] = USER_AGENT
    return client
