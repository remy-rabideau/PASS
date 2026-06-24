from datetime import datetime

from across.sdk.v1.models.schedule_create import ScheduleCreate
from across.sdk.v1.models.schedule_status import ScheduleStatus
from across.sdk.v1.models.schedule_fidelity import ScheduleFidelity
from across.sdk.v1.models.date_range import DateRange
from across.sdk.v1.models.observation_create import ObservationCreate
from across.sdk.v1.models.observation_status import ObservationStatus
from across.sdk.v1.models.observation_type import ObservationType
from across.sdk.v1.models.bandpass import Bandpass
from across.sdk.v1.models.energy_bandpass import EnergyBandpass
from across.sdk.v1.models.energy_unit import EnergyUnit
from across.sdk.v1.models.wavelength_bandpass import WavelengthBandpass
from across.sdk.v1.models.wavelength_unit import WavelengthUnit
from across.sdk.v1.models.frequency_bandpass import FrequencyBandpass
from across.sdk.v1.models.frequency_unit import FrequencyUnit
from across.sdk.v1.models.coordinate import Coordinate


OBSERVATION_TYPES = {
    "imaging": ObservationType.IMAGING,
    "timing": ObservationType.TIMING,
    "spectroscopy": ObservationType.SPECTROSCOPY,
    "slew": ObservationType.SLEW,
}


def build_bandpass(args: dict) -> Bandpass:
    """Bandpass from the activity's bandpassType + bandMin/bandMax (defaults to energy/keV)."""
    btype = (args.get("bandpassType") or "energy").lower()
    lo, hi = args.get("bandMin"), args.get("bandMax")
    if btype == "wavelength":
        return Bandpass(WavelengthBandpass(unit=WavelengthUnit.NM, min=lo, max=hi))
    if btype == "frequency":
        return Bandpass(FrequencyBandpass(unit=FrequencyUnit.GHZ, min=lo, max=hi))
    return Bandpass(EnergyBandpass(unit=EnergyUnit.KEV, min=lo, max=hi))


def _resolve_instrument(args: dict, default_uuid: str, instruments_by_name: dict) -> str:
    name = args.get("instrument")
    if name and instruments_by_name:
        return instruments_by_name.get(name, default_uuid)
    return default_uuid


def _observe_target(activity: dict, instrument_uuid: str) -> ObservationCreate:
    args = activity["attributes"]["arguments"]
    otype = (args.get("observationType") or "timing").lower()

    fields = dict(
        instrument_id=instrument_uuid,
        external_observation_id=str(args.get("acrossId") or activity["id"]),
        date_range=DateRange(
            begin=datetime.fromisoformat(activity["start_time"]),
            end=datetime.fromisoformat(activity["end_time"]),
        ),
        status=ObservationStatus.PLANNED,
        type=OBSERVATION_TYPES.get(otype, ObservationType.TIMING),
        object_name=args.get("targetName") or "UNKNOWN",
        description=args.get("description", ""),
        pointing_position=Coordinate(ra=args["ra"], dec=args["dec"]),
        bandpass=build_bandpass(args),
    )

    if otype == "slew":
        fields["pointing_angle"] = args.get("pointingAngle")
    else:
        fields["exposure_time"] = args.get("exposure")
        if otype == "timing":
            fields["t_resolution"] = args.get("tResolution")
        elif otype == "spectroscopy":
            fields["em_res_power"] = args.get("emResPower")

    return ObservationCreate(**fields)


def create_observation(
    activity: dict,
    default_instrument_uuid: str,
    instruments_by_name: dict,
) -> ObservationCreate:
    instrument_uuid = _resolve_instrument(
        activity["attributes"]["arguments"], default_instrument_uuid, instruments_by_name
    )
    return _observe_target(activity, instrument_uuid)


def build_observations(
    activities: list,
    default_instrument_uuid: str,
    instruments_by_name: dict,
) -> list:
    # only ObserveTarget activities become observations
    return [
        create_observation(a, default_instrument_uuid, instruments_by_name)
        for a in activities
        if a["activity_type_name"] == "ObserveTarget"
    ]


def create_schedule(
    sim: dict,
    plan_id: int,
    telescope_uuid: str,
    instrument_uuid: str,
    allowed_activity_types: list[str],
    instruments_by_name: dict | None = None,
) -> ScheduleCreate:
    activities = sim["simulation_datasets"][0]["simulated_activities"]

    if allowed_activity_types:
        activities = [
            a for a in activities if a["activity_type_name"] in allowed_activity_types
        ]

    return ScheduleCreate(
        telescope_id=telescope_uuid,
        name=sim["plan"]["name"],
        date_range=DateRange(
            begin=datetime.fromisoformat(sim["simulation_start_time"]),
            end=datetime.fromisoformat(sim["simulation_end_time"]),
        ),
        status=ScheduleStatus.PLANNED,
        fidelity=ScheduleFidelity.LOW,
        external_id=str(plan_id),
        observations=build_observations(
            activities, instrument_uuid, instruments_by_name or {}
        ),
    )


def observation_to_activity(obs: dict, plan_start: str) -> dict:
    """Inverse: an ACROSS observation -> a PlanDev ObserveTarget activity directive."""
    # ACROSS times and the plan start can differ in timezone awareness; compare
    # both as naive (UTC wall-clock) so the offset subtraction is well-defined.
    begin = datetime.fromisoformat(obs["begin"]).replace(tzinfo=None)
    start = datetime.fromisoformat(plan_start).replace(tzinfo=None)
    total = int((begin - start).total_seconds())
    h, rem = divmod(abs(total), 3600)
    m, s = divmod(rem, 60)
    sign = "-" if total < 0 else ""

    name = obs.get("object_name") or "ACROSS observation"
    arguments = {
        "observationType": obs.get("type") or "timing",
        "targetName": name,
        "ra": obs["ra"],
        "dec": obs["dec"],
        "exposure": obs.get("exposure_time") or 0,
    }
    if obs.get("id"):
        arguments["acrossId"] = str(obs["id"])

    return {
        "type": "ObserveTarget",
        "name": name,
        "start_offset": f"{sign}{h:02d}:{m:02d}:{s:02d}",
        "arguments": arguments,
    }
