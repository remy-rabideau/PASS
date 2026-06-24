from across.sdk.v1.api_client import ApiClient

import across_sdk
from tests.conftest import SIM


def test_forward_builds_four_observations():
    schedule = across_sdk.create_schedule(
        SIM["data"]["simulation"][0], 12,
        telescope_uuid="t", instrument_uuid="i", allowed_activity_types=[])
    obs = ApiClient().sanitize_for_serialization(schedule)["observations"]
    assert len(obs) == 4
    assert {o["type"] for o in obs} == {"timing", "slew", "imaging", "spectroscopy"}


def test_forward_type_specific_fields():
    obs = ApiClient().sanitize_for_serialization(across_sdk.create_schedule(
        SIM["data"]["simulation"][0], 12,
        telescope_uuid="t", instrument_uuid="i", allowed_activity_types=[]))["observations"]
    timing = next(o for o in obs if o["type"] == "timing")
    spec = next(o for o in obs if o["type"] == "spectroscopy")
    assert timing["t_resolution"] == 0.001
    assert spec["em_res_power"] == 1000


def test_slew_has_null_bandpass_not_string():
    obs = ApiClient().sanitize_for_serialization(across_sdk.create_schedule(
        SIM["data"]["simulation"][0], 12,
        telescope_uuid="t", instrument_uuid="i", allowed_activity_types=[]))["observations"]
    slew = next(o for o in obs if o["type"] == "slew")
    assert slew["bandpass"]["min"] is None


def test_forward_filter_by_activity_type():
    keep = across_sdk.create_schedule(
        SIM["data"]["simulation"][0], 12,
        telescope_uuid="t", instrument_uuid="i", allowed_activity_types=["ObserveTarget"])
    assert len(keep.observations) == 4
    drop = across_sdk.create_schedule(
        SIM["data"]["simulation"][0], 12,
        telescope_uuid="t", instrument_uuid="i", allowed_activity_types=["Nonexistent"])
    assert len(drop.observations) == 0


def test_inverse_mapper_offset_and_args():
    obs = {"object_name": "M31", "ra": 10.68, "dec": 41.27,
           "begin": "2026-07-20T18:56:01", "end": "2026-07-20T19:38:01",
           "exposure_time": 2520.0, "type": "imaging"}
    a = across_sdk.observation_to_activity(obs, "2026-07-20T12:00:00")
    assert a["type"] == "ObserveTarget"
    assert a["start_offset"] == "06:56:01"
    assert a["name"] == "M31"
    assert a["arguments"]["observationType"] == "imaging"
    assert a["arguments"]["ra"] == 10.68
    assert a["arguments"]["dec"] == 41.27


def test_non_observetarget_is_skipped():
    sim = {
        "simulation_start_time": "2026-07-20T12:00:00",
        "simulation_end_time": "2026-07-21T00:00:00",
        "plan": {"name": "P"},
        "simulation_datasets": [{"id": 1, "simulated_activities": [
            {"id": 9, "activity_type_name": "UnknownOp",
             "attributes": {"arguments": {}},
             "start_time": "2026-07-20T12:30:00", "end_time": "2026-07-20T12:31:00"}]}],
    }
    schedule = across_sdk.create_schedule(
        sim, 1, telescope_uuid="t", instrument_uuid="i", allowed_activity_types=[])
    assert len(schedule.observations) == 0
