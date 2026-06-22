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
    return query(SIM_QUERY, {"planId": plan_id})["data"]["simulation"][0]


INSERT_ACTIVITY_MUTATION = """
mutation InsertActivity($planId: Int!, $type: String!, $name: String!, $startOffset: interval!, $arguments: jsonb!) {
  insert_activity_directive_one(object: {
    plan_id: $planId, type: $type, name: $name, start_offset: $startOffset, arguments: $arguments
  }) { id }
}
"""


def insert_activity(plan_id: int, activity: dict) -> int:
    vars = {
        "planId": plan_id,
        "type": activity["type"],
        "name": activity["name"],
        "startOffset": activity["start_offset"],
        "arguments": activity["arguments"],
    }
    return query(INSERT_ACTIVITY_MUTATION, vars)["data"]["insert_activity_directive_one"]["id"]
