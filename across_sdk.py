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
from across.sdk.v1.models.coordinate import Coordinate


def null_bandpass() -> Bandpass:
    return Bandpass(EnergyBandpass(unit=EnergyUnit.KEV, min=None, max=None))


def energy_bandpass(arguments: dict) -> Bandpass:
    return Bandpass(
        EnergyBandpass(
            unit=EnergyUnit.KEV,
            min=arguments["energyMinKev"],
            max=arguments["energyMaxKev"],
        )
    )


OBSERVATION_MAPPERS = {}


def maps(*activity_type_names: str):
    def decorator(fn):
        for name in activity_type_names:
            OBSERVATION_MAPPERS[name] = fn
        return fn

    return decorator


def _base_fields(activity: dict, instrument_uuid: str) -> dict:
    return dict(
        instrument_id=instrument_uuid,
        external_observation_id=str(activity["id"]),
        date_range=DateRange(
            begin=datetime.fromisoformat(activity["start_time"]),
            end=datetime.fromisoformat(activity["end_time"]),
        ),
        status=ObservationStatus.PLANNED,
        type=ObservationType.TIMING,
        object_name="UNKNOWN",
        description=activity["activity_type_name"],
        bandpass=null_bandpass(),
    )


def pointing_fields(arguments: dict) -> dict:
    return dict(
        pointing_position=Coordinate(ra=arguments["ra"], dec=arguments["dec"]),
        object_name=arguments["targetName"],
        description=arguments["description"],
        exposure_time=arguments["exposure"],
        bandpass=energy_bandpass(arguments),
    )


@maps("ImageTarget")
def _imaging(activity: dict) -> dict:
    arguments = activity["attributes"]["arguments"]
    fields = pointing_fields(arguments)
    fields.update(type=ObservationType.IMAGING)
    return fields


@maps("TimeTarget")
def _timing(activity: dict) -> dict:
    arguments = activity["attributes"]["arguments"]
    fields = pointing_fields(arguments)
    fields.update(
        type=ObservationType.TIMING,
        t_resolution=arguments["tResolution"],
    )
    return fields


@maps("ObserveSpectrum")
def _observespectrum(activity: dict) -> dict:
    arguments = activity["attributes"]["arguments"]
    fields = pointing_fields(arguments)
    fields.update(
        type=ObservationType.SPECTROSCOPY,
        em_res_power=arguments["emResPower"],
    )
    return fields


@maps("Slew")
def _slew(activity: dict) -> dict:
    arguments = activity["attributes"]["arguments"]
    return dict(
        type=ObservationType.SLEW,
        pointing_position=Coordinate(ra=arguments["ra"], dec=arguments["dec"]),
        pointing_angle=arguments["pointingAngle"],
    )


def create_observation(
    activity: dict, instrument_uuid: str, unmapped: set[str]
) -> ObservationCreate:
    fields = _base_fields(activity, instrument_uuid)
    mapper = OBSERVATION_MAPPERS.get(activity["activity_type_name"])

    if mapper is not None:
        fields.update(mapper(activity))
    else:
        unmapped.add(activity["activity_type_name"])

    return ObservationCreate(**fields)


def build_observations(
    activities: list, instrument_uuid: str, unmapped: set[str]
) -> list:
    return [create_observation(a, instrument_uuid, unmapped) for a in activities]


def create_schedule(
    sim: dict,
    plan_id: int,
    telescope_uuid: str,
    instrument_uuid: str,
    allowed_activity_types: list[str],
) -> ScheduleCreate:
    activities = sim["simulation_datasets"][0]["simulated_activities"]

    if allowed_activity_types:
        activities = [
            a for a in activities if a["activity_type_name"] in allowed_activity_types
        ]

    unmapped: set[str] = set()

    schedule = ScheduleCreate(
        telescope_id=telescope_uuid,
        name=sim["plan"]["name"],
        date_range=DateRange(
            begin=datetime.fromisoformat(sim["simulation_start_time"]),
            end=datetime.fromisoformat(sim["simulation_end_time"]),
        ),
        status=ScheduleStatus.PLANNED,
        fidelity=ScheduleFidelity.LOW,
        external_id=str(plan_id),
        observations=build_observations(activities, instrument_uuid, unmapped),
    )

    if unmapped:
        print(
            "No mapper for these activity types (used placeholders):",
            sorted(unmapped),
        )

    return schedule


def observation_to_activity(obs: dict, plan_start: str) -> dict:
    begin = datetime.fromisoformat(obs["begin"])
    start = datetime.fromisoformat(plan_start)
    offset = begin - start
    total = int(offset.total_seconds())
    h, rem = divmod(abs(total), 3600)
    m, s = divmod(rem, 60)
    sign = "-" if total < 0 else ""
    return {
        "type": "ObserveTarget",
        "name": obs.get("object_name") or "ACROSS observation",
        "start_offset": f"{sign}{h:02d}:{m:02d}:{s:02d}",
        "arguments": {
            "ra": obs["ra"],
            "dec": obs["dec"],
            "exposure": obs.get("exposure_time") or 0,
        },
    }
