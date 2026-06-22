import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

os.environ["HASURA_URL"] = "http://127.0.0.1:8077/"
os.environ["HASURA_ADMIN_SECRET"] = "test"
os.environ["ACROSS_CLIENT_ID"] = ""
os.environ["ACROSS_CLIENT_SECRET"] = ""

import pytest

MISC = os.path.join(os.path.dirname(__file__), "..", "misc")

raw = open(os.path.join(MISC, "across_activities_from_plandev.txt")).read().strip()
ACTS = json.loads("[" + raw.rstrip(",") + "]")
for a in ACTS:
    a["id"] = a["attributes"]["directiveId"]
    a["start_time"] = "2026-07-20T13:00:00"
    a["end_time"] = "2026-07-20T13:01:00"
    a["duration"] = "00:01:00"
    a["simulation_dataset_id"] = 36

PLANS = {"data": {"plan": [{"name": "Mars ACROSS Plan", "id": 12,
    "simulations": [{"id": 8, "simulation_datasets": [{"id": 36, "status": "success"}]}]}]}}
TYPES = {"data": {"simulation": [{"simulation_datasets": [{"simulated_activities":
    [{"activity_type_name": t} for t in sorted({a["activity_type_name"] for a in ACTS})]}]}]}}
SIM = {"data": {"simulation": [{
    "simulation_start_time": "2026-07-20T12:00:00",
    "simulation_end_time": "2026-07-21T00:00:00",
    "plan": {"name": "Mars ACROSS Plan", "mission_model": {"name": "MarsSat"}},
    "simulation_datasets": [{"id": 36, "status": "success", "simulated_activities": ACTS}]}]}}

WRITES = []


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or "{}")
        q = body.get("query", "")
        if "GetPlans" in q:
            r = PLANS
        elif "GetActivityTypes" in q:
            r = TYPES
        elif "GetLatestSimulation" in q:
            r = SIM
        elif "insert_activity_directive_one" in q:
            WRITES.append(body.get("variables"))
            r = {"data": {"insert_activity_directive_one": {"id": len(WRITES)}}}
        else:
            r = {"data": {}}
        out = json.dumps(r).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)


@pytest.fixture(scope="session", autouse=True)
def fake_plandev():
    os.environ["HASURA_URL"] = "http://127.0.0.1:8077/"
    os.environ["HASURA_ADMIN_SECRET"] = "test"
    os.environ["ACROSS_CLIENT_ID"] = ""
    os.environ["ACROSS_CLIENT_SECRET"] = ""
    srv = HTTPServer(("127.0.0.1", 8077), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.3)
    yield
    srv.shutdown()


@pytest.fixture()
def client():
    import app
    return app.app.test_client()


@pytest.fixture(autouse=True)
def reset_writes():
    WRITES.clear()
    yield


@pytest.fixture()
def writes():
    return WRITES
