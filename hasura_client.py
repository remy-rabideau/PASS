import requests
from config import HASURA_URL, HASURA_ADMIN_SECRET


def query(query: str, vars: dict) -> dict:

    response = requests.post(
        HASURA_URL,
        headers={
            "x-hasura-admin-secret": HASURA_ADMIN_SECRET,
            "Content-Type": "application/json",
        },
        json={"query": query, "variables": vars},
    )

    response.raise_for_status()

    return response.json()


SIM_QUERY = """
query GetLatestSimulation($planId: Int!) {
  simulation(where: { plan_id: { _eq: $planId } }) {
    simulation_start_time
    simulation_end_time
    plan {
      name
      mission_model {
        name
      }
    }
    simulation_datasets(order_by: { id: desc }, limit: 1) {
      id
      status
      simulated_activities {
        id
        activity_type_name
        attributes
        duration
        start_time
        end_time
        start_offset
        simulation_dataset_id
      }
    }
  }
}
"""


def get_simulation(plan_id: int) -> dict:
    return query(SIM_QUERY, {"planId": plan_id})["data"]["simulation"][0]


RESOURCE_QUERY = """
query GetResourceAtOffset($datasetId: Int!, $startOffset: interval!, $resource: String!) {
  getResourcesAtStartOffset(
    args: { _dataset_id: $datasetId, _start_offset: $startOffset },
    where: { name: { _eq: $resource } }
  ) {
    name
    dynamics
  }
}
"""

def get_resource_at_time(simulation_dataset_id: int, resource: str, offset: str):

    vars = {
        "datasetId": simulation_dataset_id,
        "startOffset": offset_to_interval(offset),
        "resource": resource,
    }

    return query(RESOURCE_QUERY, vars)["data"]["getResourcesAtStartOffset"][0]["dynamics"]


RESOURCES_QUERY = """
query GetResourcesAtOffset($datasetId: Int!, $startOffset: interval!, $regex: String!) {
  getResourcesAtStartOffset(args: {_dataset_id: $datasetId, _start_offset: $startOffset}, where: {name: {_regex: $regex}}) {
    name
    dynamics
  }
}
"""

def get_constant_resources(simulation_dataset_id: int, resource_regex: str):

    vars = {
        "datasetId": simulation_dataset_id,
        "startOffset": offset_to_interval("0:0:0"),
        "regex": resource_regex,
    }

    return query(RESOURCES_QUERY, vars)["data"]["getResourcesAtStartOffset"]


def offset_to_interval(offset: str) -> str:

    parts = offset.strip().split()

    total_seconds = 0.0

    if len(parts) == 3 and parts[1] == "day":
        days = int(parts[0])
        total_seconds += days * 86400
        time_part = parts[2]
    elif len(parts) == 1:
        time_part = parts[0]
    else:
        raise ValueError(f"Unexpected offset format: {offset}")

    time_components = time_part.split(":")
    hours = int(time_components[0])
    minutes = int(time_components[1])
    seconds = float(time_components[2])

    total_seconds += hours * 3600 + minutes * 60 + seconds
    
    # Add 1 microsecond to ensure slew has fully settled
    total_seconds += 0.000001

    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = total_seconds % 60

    return f"{h:02d}:{m:02d}:{s:09.6f}"


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
    payload = query(_PLANS_QUERY, {})['data']
    if 'errors' in payload:
        raise RuntimeError(f'Hasura error: {payload["errors"]}')

    plans = []
    for p in payload['plan']:
        sims = p.get('simulations') or []
        sim_id = sims[0]['id'] if sims else None
        datasets = (sims[0].get('simulation_datasets') if sims else None) or []
        dataset_status = datasets[0]['status'] if datasets else None

        plans.append({
            'name': p['name'],
            'id': p['id'],
            'simulation_id': sim_id,
            'dataset_status': dataset_status,
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
    payload = query(_ACTIVITY_TYPES_QUERY, {'planId': plan_id})['data']
    if 'errors' in payload:
        raise RuntimeError(f'Hasura error: {payload["errors"]}')

    sims = payload['simulation']
    if not sims:
        return []
    types = sims[0]['simulation_datasets'][0]['simulated_activities']
    return sorted(t['activity_type_name'] for t in types)


