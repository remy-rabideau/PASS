"""ACROSS events -> PlanDev external events (the plan-timeline overlay).

External activity from ACROSS is read and written into PlanDev as external
events, so it appears on a plan's timeline as context the planner reacts to.
Two real ACROSS sources are supported, in priority order:

  1. Broker events  -> multi-messenger alerts (gravitational-wave / GRB /
     neutrino). The flagship case; used whenever ACROSS has any.
  2. Observations   -> other observatories' planned/observed targets. Abundant
     real data, used when there are no live broker events.

A labelled sample is used only if ACROSS is unreachable, so the overlay is
always demonstrable.

Three systems are touched, each through its own interface:
  - ACROSS    REST  GET /broker-event/, GET /observation/   (read)
  - Gateway   REST  /uploadExternalSourceEventTypes,
                    /uploadExternalSource                    (write)
  - Hasura    GraphQL                                        (link group->plan)
"""
import json
import re
from datetime import datetime, timedelta

import requests

from across_data import ACROSS_API, get_nearby_observations
from hasura_client import query
from config import GATEWAY_URL

SOURCE_TYPE = "ACROSSEventSource"
EVENT_TYPE = "ACROSSEvent"
DERIVATION_GROUP = "across-events"

# how long a block each event occupies on the timeline
BLOCK = timedelta(hours=1)

# a real region to draw observations from when there are no broker alerts
OBS_RA, OBS_DEC, OBS_RADIUS = 180.2, 4.9, 10.0

# attribute schema for the event type, uploaded once. The gateway expects each
# map of types as a JSON string, not a nested object.
EVENT_TYPE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "kind": {"type": "string"},
        "origin": {"type": "string"},
        "ra": {"type": "number"},
        "dec": {"type": "number"},
        "exposure": {"type": "number"},
        "probability": {"type": "number"},
        "acrossId": {"type": "string"},
        "observedAt": {"type": "string"},
    },
    "required": ["name", "kind"],
}
SOURCE_TYPE_SCHEMA = {
    "type": "object",
    "properties": {"origin": {"type": "string"}},
    "required": ["origin"],
}


# --- time helpers -----------------------------------------------------------
# The gateway parses timestamps without a timezone offset, so everything is
# normalized to naive "YYYY-MM-DDTHH:MM:SS".

def _naive(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "")).replace(tzinfo=None)


def _fmt(dt: datetime) -> str:
    return dt.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S")


def _hms(td: timedelta) -> str:
    total = max(0, int(td.total_seconds()))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _parse_interval(s: str) -> timedelta:
    days = int(m.group(1)) if (m := re.search(r"(\d+)\s+day", s)) else 0
    h = mn = sec = 0
    if t := re.search(r"(\d+):(\d+):(\d+)", s):
        h, mn, sec = int(t.group(1)), int(t.group(2)), int(t.group(3))
    return timedelta(days=days, hours=h, minutes=mn, seconds=sec)


# --- ACROSS read (normalized to a common event shape) -----------------------

def get_broker_events(limit: int = 20) -> list[dict]:
    """Multi-messenger broker events from ACROSS, as common event dicts."""
    response = requests.get(
        f"{ACROSS_API}/broker-event/",
        params={"page": 1, "page_limit": limit},
        timeout=30,
    )
    response.raise_for_status()

    events = []
    for e in response.json().get("items", []):
        loc = (e.get("localizations") or [{}])[0]
        events.append({
            "id": str(e.get("id")),
            "name": e.get("name") or str(e.get("id")),
            "kind": e.get("type") or "alert",
            "origin": "broker",
            "ra": loc.get("ra"),
            "dec": loc.get("dec"),
            "probability": loc.get("probability_enclosed"),
            "observed_at": e.get("event_datetime"),
        })
    return events


def get_observation_events(limit: int = 6) -> list[dict]:
    """Other observatories' observations from ACROSS, as common event dicts."""
    events = []
    for o in get_nearby_observations(OBS_RA, OBS_DEC, OBS_RADIUS, limit=limit):
        events.append({
            "id": str(o.get("id")),
            "name": o.get("object_name") or str(o.get("id")),
            "kind": o.get("type") or "observation",
            "origin": "observation",
            "ra": o.get("ra"),
            "dec": o.get("dec"),
            "exposure": o.get("exposure_time"),
            "observed_at": o.get("begin"),
        })
    return events


def sample_events(plan_start: datetime) -> list[dict]:
    """Representative events for when ACROSS is unreachable (demo only)."""
    return [
        {"id": "SAMPLE-GW", "name": "GW260701 NS-merger", "kind": "gw",
         "origin": "sample", "ra": 197.45, "dec": -23.38, "probability": 0.90,
         "observed_at": _fmt(plan_start + timedelta(hours=6))},
        {"id": "SAMPLE-GRB", "name": "GRB 260701A", "kind": "grb",
         "origin": "sample", "ra": 88.79, "dec": 7.41, "probability": 0.95,
         "observed_at": _fmt(plan_start + timedelta(hours=14))},
    ]


# --- PlanDev write ----------------------------------------------------------

def _gateway_token() -> str:
    """Mint a gateway token. Local PlanDev runs AUTH_TYPE=none, so any user works."""
    response = requests.post(
        f"{GATEWAY_URL}/auth/login",
        json={"username": "aerie", "password": "aerie"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["token"]


def _build_source(events: list[dict], plan_start: datetime, plan_end: datetime,
                  source_key: str) -> dict:
    """Assemble the external-source document. Events are spaced evenly across the
    plan window so they are visible on the timeline; their real coordinates and
    observation time are preserved in the attributes."""
    span = (plan_end - plan_start) / (len(events) + 1)
    event_docs = []
    for i, e in enumerate(events):
        start = plan_start + span * (i + 1)
        duration = min(BLOCK, plan_end - start)
        attrs = {"name": e["name"], "kind": e["kind"], "origin": e["origin"],
                 "ra": e.get("ra") or 0.0, "dec": e.get("dec") or 0.0,
                 "acrossId": e["id"]}
        if e.get("exposure") is not None:
            attrs["exposure"] = e["exposure"]
        if e.get("probability") is not None:
            attrs["probability"] = e["probability"]
        if e.get("observed_at"):
            attrs["observedAt"] = e["observed_at"]
        event_docs.append({
            "key": e["id"],
            "event_type_name": EVENT_TYPE,
            "start_time": _fmt(start),
            "duration": _hms(duration),
            "attributes": attrs,
        })

    return {
        "source": {
            "key": source_key,
            "source_type_name": SOURCE_TYPE,
            "derivation_group_name": DERIVATION_GROUP,
            "valid_at": _fmt(datetime.now()),
            "period": {"start_time": _fmt(plan_start), "end_time": _fmt(plan_end)},
            "attributes": {"origin": ACROSS_API},
        },
        "events": event_docs,
    }


def _upload_types(token: str) -> None:
    body = {
        "event_types": json.dumps({EVENT_TYPE: EVENT_TYPE_SCHEMA}),
        "source_types": json.dumps({SOURCE_TYPE: SOURCE_TYPE_SCHEMA}),
    }
    response = requests.post(
        f"{GATEWAY_URL}/uploadExternalSourceEventTypes",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        data=json.dumps(body),
        timeout=30,
    )
    response.raise_for_status()


def _upload_source(token: str, source: dict) -> dict:
    files = {
        "external_source_file": (
            source["source"]["key"], json.dumps(source), "application/json",
        )
    }
    response = requests.post(
        f"{GATEWAY_URL}/uploadExternalSource",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        data={"derivation_group_name": DERIVATION_GROUP},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


PLAN_QUERY = """
query Plan($planId: Int!) {
  plan(where: { id: { _eq: $planId } }, limit: 1) { start_time duration }
}
"""

LINK_MUTATION = """
mutation Link($planId: Int!, $dg: String!) {
  insert_plan_derivation_group_one(
    object: { plan_id: $planId, derivation_group_name: $dg }
    on_conflict: { constraint: plan_derivation_group_pkey, update_columns: [] }
  ) { plan_id derivation_group_name }
}
"""


def _plan_window(plan_id: int) -> tuple[datetime, datetime]:
    rows = query(PLAN_QUERY, {"planId": plan_id})["data"]["plan"]
    if not rows:
        raise RuntimeError(f"Plan {plan_id} not found")
    start = _naive(rows[0]["start_time"])
    return start, start + _parse_interval(rows[0]["duration"])


def _link_to_plan(plan_id: int) -> None:
    query(LINK_MUTATION, {"planId": plan_id, "dg": DERIVATION_GROUP})


# --- orchestrator -----------------------------------------------------------

def _fetch_events(plan_start: datetime) -> tuple[list[dict], str]:
    """Real ACROSS data first (broker alerts, then observations); sample last."""
    try:
        broker = get_broker_events()
        if broker:
            return broker, "broker alerts"
    except requests.RequestException:
        pass
    try:
        observations = get_observation_events()
        if observations:
            return observations, "ACROSS observations"
    except requests.RequestException:
        pass
    return sample_events(plan_start), "sample (ACROSS unreachable)"


def sync_alerts(plan_id: int) -> dict:
    """Pull ACROSS events and overlay them on the plan as external events."""
    plan_start, plan_end = _plan_window(plan_id)
    events, origin = _fetch_events(plan_start)

    token = _gateway_token()
    source_key = f"across-events-{_fmt(datetime.now()).replace(':', '')}.json"
    source = _build_source(events, plan_start, plan_end, source_key)

    _upload_types(token)
    _upload_source(token, source)
    _link_to_plan(plan_id)

    return {
        "count": len(events),
        "origin": origin,
        "source_key": source_key,
        "derivation_group": DERIVATION_GROUP,
        "events": [
            {"name": e["name"], "kind": e["kind"], "ra": e.get("ra"),
             "dec": e.get("dec"), "observed_at": e.get("observed_at")}
            for e in events
        ],
    }
