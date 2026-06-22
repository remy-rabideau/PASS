import requests

from across.sdk.v1.configuration import Configuration
from across.sdk.v1.api_client_wrapper import ApiClientWrapper
from across.sdk.v1.api.telescope_api import TelescopeApi

from hasura_client import query

ACROSS_API = "https://api.across.sciencecloud.nasa.gov/v1"


def get_nearby_observations(ra: float, dec: float, radius: float, limit: int = 20) -> list[dict]:
    response = requests.get(
        f"{ACROSS_API}/observation/",
        params={
            "cone_search_ra": ra,
            "cone_search_dec": dec,
            "cone_search_radius": radius,
            "page": 1,
            "page_limit": limit,
        },
        timeout=30,
    )
    response.raise_for_status()

    result = []
    for o in response.json()["items"]:
        result.append({
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


_PLANS_QUERY = """
query GetPlans {
  plan(order_by: { name: asc }) {
    id
    name
    simulations(order_by: { id: desc }, limit: 1) {
      id
      simulation_datasets(order_by: { id: desc }, limit: 1) {
        id
        status
      }
    }
  }
}
"""


def get_plans() -> list[dict]:
    payload = query(_PLANS_QUERY, {})

    plans = []
    for p in payload["data"]["plan"]:
        sims = p.get("simulations") or []
        sim_id = sims[0]["id"] if sims else None
        datasets = (sims[0].get("simulation_datasets") if sims else None) or []
        dataset_status = datasets[0]["status"] if datasets else None

        plans.append({
            "name": p["name"],
            "id": p["id"],
            "simulation_id": sim_id,
            "dataset_status": dataset_status,
        })

    return plans


_ACTIVITY_TYPES_QUERY = """
query GetActivityTypes($planId: Int!) {
  simulation(where: { plan_id: { _eq: $planId } }) {
    simulation_datasets(order_by: { id: desc }, limit: 1) {
      simulated_activities(distinct_on: activity_type_name) {
        activity_type_name
      }
    }
  }
}
"""


def get_activity_types(plan_id: int) -> list[str]:
    payload = query(_ACTIVITY_TYPES_QUERY, {"planId": plan_id})

    sims = payload["data"]["simulation"]
    if not sims:
        return []
    types = sims[0]["simulation_datasets"][0]["simulated_activities"]
    return sorted(t["activity_type_name"] for t in types)
