from flask import Flask, render_template, request

from across.client import Client
from across.sdk.v1.api_client import ApiClient
from across.sdk.v1.models.schedule_status import ScheduleStatus
from across.sdk.v1.models.schedule_fidelity import ScheduleFidelity

from across_sdk import create_schedule
from across_data import get_telescopes, get_plans, get_activity_types
from hasura_client import get_simulation
from config import ACROSS_CLIENT_ID, ACROSS_CLIENT_SECRET

app = Flask(__name__)

FIDELITIES = [e.value for e in ScheduleFidelity]
STATUSES = [e.value for e in ScheduleStatus]


def _find(items: list[dict], name: str) -> dict | None:
    return next((i for i in items if i["name"] == name), None)


def _send(plan, telescope, instrument, fidelity, status, allowed_types) -> str:
    simulation = get_simulation(plan["id"])
    schedule = create_schedule(
        simulation,
        plan["id"],
        telescope_uuid=telescope["id"],
        instrument_uuid=instrument["id"],
        allowed_activity_types=allowed_types,
    )
    schedule.fidelity = ScheduleFidelity(fidelity)
    schedule.status = ScheduleStatus(status)

    print(ApiClient().sanitize_for_serialization(schedule))

    client = Client(client_id=ACROSS_CLIENT_ID, client_secret=ACROSS_CLIENT_SECRET)
    new_id = client.schedule.post(schedule=schedule)
    return f"Sent {len(schedule.observations)} observation(s). ACROSS schedule id: {new_id}"


@app.route("/", methods=["GET", "POST"])
def index():
    form = request.form
    telescope_name = form.get("telescope", "")
    instrument_name = form.get("instrument", "")
    plan_name = form.get("plan", "")
    fidelity = form.get("fidelity", ScheduleFidelity.LOW.value)
    status = form.get("status", ScheduleStatus.PLANNED.value)
    selected_types = form.getlist("activity_types")

    message = None
    error = None

    telescopes = []
    instruments = []
    plans = []
    activity_types = []
    telescope = instrument = plan = None
    try:
        telescopes = get_telescopes()
        telescope = _find(telescopes, telescope_name)
        instruments = telescope["instruments"] if telescope else []
        instrument = _find(instruments, instrument_name)
        plans = get_plans() if instrument else []
        plan = _find(plans, plan_name)
        activity_types = get_activity_types(plan["id"]) if plan else []
    except Exception as e:
        error = f"Could not load data: {e}"

    if not error and form.get("action") == "send":
        if plan is None:
            error = "Pick a plan first."
        else:
            try:
                message = _send(
                    plan, telescope, instrument, fidelity, status,
                    selected_types or activity_types,
                )
            except Exception as e:
                error = f"Send failed: {e}"

    return render_template(
        "index.html",
        telescopes=[t["name"] for t in telescopes],
        instruments=[i["name"] for i in instruments],
        plans=[p["name"] for p in plans],
        activity_types=activity_types,
        fidelities=FIDELITIES,
        statuses=STATUSES,
        selected={
            "telescope": telescope_name,
            "instrument": instrument_name,
            "plan": plan_name,
            "fidelity": fidelity,
            "status": status,
            "activity_types": selected_types,
        },
        can_send=plan is not None,
        message=message,
        error=error,
    )


if __name__ == "__main__":
    app.run(debug=True)
