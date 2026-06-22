from flask import Flask, render_template, request

from across.client import Client
from across.sdk.v1.api_client import ApiClient
from across.sdk.v1.models.schedule_status import ScheduleStatus
from across.sdk.v1.models.schedule_fidelity import ScheduleFidelity

from across_sdk import create_schedule, observation_to_activity
from across_data import (
    get_telescopes,
    get_plans,
    get_activity_types,
    get_nearby_observations,
    resolve_object,
    get_visibility_windows,
)
from hasura_client import get_simulation, insert_activity
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


@app.route("/visibility", methods=["GET", "POST"])
def visibility():
    form = request.form
    object_name = form.get("object_name", "")
    begin = form.get("begin", "2026-07-01T00:00:00")
    end = form.get("end", "2026-07-02T00:00:00")
    instrument_name = form.get("instrument", "")

    message = None
    error = None
    instruments = []
    resolved = None
    windows = []
    nearby = []
    try:
        instruments = []
        for t in get_telescopes():
            for inst in t["instruments"]:
                instruments.append({"name": f"{t['name']} / {inst['name']}", "id": inst["id"]})
        if object_name and form.get("action") == "check":
            resolved = resolve_object(object_name)
            instrument = next((i for i in instruments if i["name"] == instrument_name), None)
            if instrument:
                windows = get_visibility_windows(
                    instrument["id"], resolved["ra"], resolved["dec"], begin, end
                )
            nearby = get_nearby_observations(resolved["ra"], resolved["dec"], 5)
    except Exception as e:
        error = f"Could not load data: {e}"

    return render_template(
        "visibility.html",
        instruments=[i["name"] for i in instruments],
        selected={"object_name": object_name, "begin": begin, "end": end, "instrument": instrument_name},
        resolved=resolved,
        windows=windows,
        nearby=nearby,
        message=message,
        error=error,
    )


@app.route("/import", methods=["GET", "POST"])
def import_observations():
    form = request.form
    plan_name = form.get("plan", "")
    ra = form.get("ra", "")
    dec = form.get("dec", "")
    radius = form.get("radius", "5")

    message = None
    error = None
    observations = []
    plans = []
    plan = None
    try:
        plans = get_plans()
        plan = _find(plans, plan_name)
        if ra and dec:
            observations = get_nearby_observations(float(ra), float(dec), float(radius))
    except Exception as e:
        error = f"Could not load data: {e}"

    if not error and form.get("action") == "import" and observations:
        if plan is None:
            error = "Pick a plan first."
        else:
            try:
                sim = get_simulation(plan["id"])
                plan_start = sim["simulation_start_time"]
                chosen = form.getlist("obs")
                count = 0
                for i in chosen:
                    activity = observation_to_activity(observations[int(i)], plan_start)
                    insert_activity(plan["id"], activity)
                    count += 1
                message = f"Imported {count} observation(s) into plan '{plan['name']}'."
            except Exception as e:
                error = f"Import failed: {e}"

    return render_template(
        "import.html",
        plans=[p["name"] for p in plans],
        observations=observations,
        selected={"plan": plan_name, "ra": ra, "dec": dec, "radius": radius},
        message=message,
        error=error,
    )


if __name__ == "__main__":
    app.run(debug=True)
