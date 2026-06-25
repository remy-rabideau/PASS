import requests
from config import HASURA_URL, HASURA_ADMIN_SECRET


def query(query: str, vars: dict) -> dict:
    """Send a GraphQL query/mutation to Hasura; raise on errors, return the JSON."""
    response = requests.post(
        HASURA_URL,
        headers={
            "x-hasura-admin-secret": HASURA_ADMIN_SECRET,
            "Content-Type": "application/json",
        },
        json={"query": query, "variables": vars},
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()
    if "errors" in payload:
        raise RuntimeError(f"Hasura error: {payload['errors']}")

    return payload


SIM_QUERY = """
query GetLatestSimulation($planId: Int!) {
  simulation(where: { plan_id: { _eq: $planId } }, order_by: { id: desc }, limit: 1) {
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
        simulation_dataset_id
      }
    }
  }
}
"""


def get_simulation(plan_id: int) -> dict:
    """Read a plan's latest simulation, including its simulated activities."""
    return query(SIM_QUERY, {"planId": plan_id})["data"]["simulation"][0]


INSERT_ACTIVITY_MUTATION = """
mutation InsertActivity($planId: Int!, $type: String!, $name: String!, $startOffset: interval!, $arguments: jsonb!) {
  insert_activity_directive_one(object: {
    plan_id: $planId, type: $type, name: $name, start_offset: $startOffset, arguments: $arguments
  }) { id }
}
"""


def insert_activity(plan_id: int, activity: dict) -> int:
    """Insert one activity directive into a plan; return its new id."""
    vars = {
        "planId": plan_id,
        "type": activity["type"],
        "name": activity["name"],
        "startOffset": activity["start_offset"],
        "arguments": activity["arguments"],
    }
    return query(INSERT_ACTIVITY_MUTATION, vars)["data"]["insert_activity_directive_one"]["id"]


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
    """PlanDev plans with their latest simulation id + status."""
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
    """Distinct activity-type names in a plan's latest simulation."""
    payload = query(_ACTIVITY_TYPES_QUERY, {"planId": plan_id})

    sims = payload["data"]["simulation"]
    if not sims:
        return []
    types = sims[0]["simulation_datasets"][0]["simulated_activities"]
    return sorted(t["activity_type_name"] for t in types)
