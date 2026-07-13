"""
ACROSS API calls.

- get_telescopes(): pulls telescopes from the ACROSS API.
- short_name_to_uuid(): resolves an instrument short name to its ACROSS UUID.
"""

from across.sdk.v1.configuration import Configuration
from across.sdk.v1.api_client_wrapper import ApiClientWrapper
from across.sdk.v1.api.telescope_api import TelescopeApi
from across.sdk.v1.api.instrument_api import InstrumentApi

HOST = "http://localhost:8000/v1"

# ---------------------------------------------------------------------------
# ACROSS: telescopes
# ---------------------------------------------------------------------------

def get_telescopes() -> list[dict]:
    """
    Return telescopes shaped for the UI:

        [
          {"name": "MyTelescope", "id": "uuid-..."},
          ...
        ]
    """

    config = Configuration(host=HOST)
    client = ApiClientWrapper.get_client(configuration=config)
    api = TelescopeApi(client)
    telescopes = api.get_telescopes()

    return [{"name": t.name, "id": t.id} for t in telescopes]


def short_name_to_uuid(short_name: str) -> str:
    """Return the ACROSS instrument UUID for the given short name."""

    config = Configuration(host=HOST)
    client = ApiClientWrapper.get_client(configuration=config)
    api = InstrumentApi(client)
    instruments = api.get_instruments()

    for inst in instruments:
        if inst.short_name == short_name:
            return inst.id

    raise ValueError(f"No instrument found with short name: {short_name!r}")

