import requests

from across.sdk.v1.configuration import Configuration
from across.sdk.v1.api_client_wrapper import ApiClientWrapper
from across.sdk.v1.api.telescope_api import TelescopeApi

ACROSS_API = "https://api.across.sciencecloud.nasa.gov/v1"


def get_nearby_observations(ra: float, dec: float, radius: float, limit: int = 20,
                            begin: str | None = None, end: str | None = None) -> list[dict]:
    """ACROSS observations within `radius` degrees of a sky point (cone search),
    optionally limited to a date range."""
    params = {
        "cone_search_ra": ra,
        "cone_search_dec": dec,
        "cone_search_radius": radius,
        "page": 1,
        "page_limit": limit,
    }
    if begin:
        params["date_range_begin"] = begin
    if end:
        params["date_range_end"] = end
    response = requests.get(f"{ACROSS_API}/observation/", params=params, timeout=30)
    response.raise_for_status()

    result = []
    for o in response.json()["items"]:
        result.append({
            "id": o.get("id"),
            "object_name": o.get("object_name"),
            "ra": o["pointing_position"]["ra"],
            "dec": o["pointing_position"]["dec"],
            "begin": o["date_range"]["begin"],
            "end": o["date_range"]["end"],
            "type": o.get("type"),
            "exposure_time": o.get("exposure_time"),
        })
    return result


def resolve_object(object_name: str) -> dict:
    """Resolve an object name to RA/Dec via ACROSS (name lookup, e.g. CDS)."""
    response = requests.get(
        f"{ACROSS_API}/tools/resolve-object/",
        params={"object_name": object_name},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    return {"ra": data["ra"], "dec": data["dec"], "resolver": data.get("resolver")}


def get_visibility_windows(
    instrument_id: str, ra: float, dec: float, begin: str, end: str
) -> list[dict]:
    """Ask ACROSS when an instrument can observe a target over a time range."""
    response = requests.get(
        f"{ACROSS_API}/tools/visibility-calculator/windows/{instrument_id}",
        params={
            "ra": ra,
            "dec": dec,
            "date_range_begin": begin,
            "date_range_end": end,
        },
        timeout=60,
    )
    response.raise_for_status()

    result = []
    for w in response.json()["visibility_windows"]:
        result.append({
            "begin": w["window"]["begin"]["datetime"],
            "end": w["window"]["end"]["datetime"],
            "duration": w["max_visibility_duration"],
        })
    return result


def get_telescopes() -> list[dict]:
    """ACROSS telescopes, each with its instruments (name + UUID)."""
    config = Configuration(host="https://api.across.sciencecloud.nasa.gov/v1")
    client = ApiClientWrapper.get_client(configuration=config)
    api = TelescopeApi(client)
    telescopes = api.get_telescopes()

    result = []
    for t in telescopes:
        instruments = [
            {"name": inst.name, "id": inst.id}
            for inst in (t.instruments or [])
        ]
        result.append({"name": t.name, "id": t.id, "instruments": instruments})

    return result
