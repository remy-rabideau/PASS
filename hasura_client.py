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
