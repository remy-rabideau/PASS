import requests
from config import HASURA_URL, HASURA_ADMIN_SECRET

QUERY = """
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
        simulation_dataset_id
      }
    }
  }
}
"""

def get_simulation(plan_id: int) -> dict:
    response = requests.post(
        HASURA_URL,
        headers={
            "x-hasura-admin-secret": HASURA_ADMIN_SECRET,
            "Content-Type": "application/json",
        },
        json={
            "query": QUERY,
            "variables": {"planId": plan_id}
        }
    )
    response.raise_for_status()
    return response.json()["data"]["simulation"][0]


# if __name__ == "__main__":
#     print(get_simulated_activities(3))