"""
Data sources for the schedule UI.

- get_telescopes(): pulls telescopes (and their instruments) from the ACROSS API.
- get_plans(): pulls plans + most recent simulation id from the PlanDev Hasura API.

Both return plain Python structures the UI can drop straight into dropdowns.
"""

import requests

from across.sdk.v1.configuration import Configuration
from across.sdk.v1.api_client_wrapper import ApiClientWrapper
from across.sdk.v1.api.telescope_api import TelescopeApi

from config import HASURA_URL, HASURA_ADMIN_SECRET


# ---------------------------------------------------------------------------
# ACROSS: telescopes + instruments
# ---------------------------------------------------------------------------

def get_telescopes() -> list[dict]:
    """
    Return telescopes with their instruments, shaped for the UI:

        [
          {
            "name": "MyTelescope",
            "id": "uuid-...",
            "instruments": [{"name": "RadarA", "id": "uuid-..."}, ...],
          },
          ...
        ]
    """

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


# ---------------------------------------------------------------------------
# PlanDev (Hasura): plans + most recent simulation id
# ---------------------------------------------------------------------------

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
    """
    Return plans with their id and most recent simulation id, shaped for the UI:

        [
          {
            "name": "Test Plan 3",
            "id": 3,
            "simulation_id": 8,          # most recent simulation, or None
            "dataset_status": "success", # status of its latest dataset, or None
          },
          ...
        ]
    """
    response = requests.post(
        HASURA_URL,
        headers={
            "x-hasura-admin-secret": HASURA_ADMIN_SECRET,
            "Content-Type": "application/json",
        },
        json={"query": _PLANS_QUERY},
    )
    response.raise_for_status()

    payload = response.json()
    if "errors" in payload:
        raise RuntimeError(f"Hasura error: {payload['errors']}")

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
    """Return the activity type names defined by the plan's mission model."""
    response = requests.post(
        HASURA_URL,
        headers={
            "x-hasura-admin-secret": HASURA_ADMIN_SECRET,
            "Content-Type": "application/json",
        },
        json={"query": _ACTIVITY_TYPES_QUERY, "variables": {"planId": plan_id}},
    )
    response.raise_for_status()

    payload = response.json()
    if "errors" in payload:
        raise RuntimeError(f"Hasura error: {payload['errors']}")

    sims = payload["data"]["simulation"]
    if not sims:
        return []
    types = sims[0]["simulation_datasets"][0]["simulated_activities"]
    return sorted(t["activity_type_name"] for t in types)