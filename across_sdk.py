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

from config import *

TELESCOPE_UUID = ""
INSTRUMENT_UUID = ""
ALLOWED_ACTIVITY_TYPES = []

# ---------------------------------------------------------------------------
# -- Helpers
# ---------------------------------------------------------------------------


def arg(arguments: dict, key: str, default=None):
    """
    Read one argument. PlanDev sometimes wraps a value as
    {"value": ..., "present": bool} and sometimes stores it bare,
    so normalize both forms.
    """

    val = arguments.get(key, default)
    if isinstance(val, dict) and "present" in val:
        return val["value"] if val.get("present") else default
    
    return val

def arg_num(arguments: dict, key: str, default=None) -> float | int | None:

    val = arg(arguments, key, default)
    if isinstance(val, (int, float)):
        return val
    
    return default
 
def null_bandpass() -> Bandpass:
    """Placeholder for activities that collect no EM radiation (slews, ops)."""

    return Bandpass(EnergyBandpass(unit=EnergyUnit.KEV, min=None, max=None))


# ---------------------------------------------------------------------------
# -- Mapper registry -- Add activity types here
# ---------------------------------------------------------------------------


# activity_type_name -> function(activity) -> dict of ObservationCreate kwargs
OBSERVATION_MAPPERS = {}
 
# Activity types seen at runtime with no registered mapper. Inspect this after
# a run to discover what a new model contains.
UNMAPPED_TYPES: set[str] = set()

def maps(*activity_type_names: str):
    """Decorator to register a mapper for one or more activity type names."""

    def decorator(fn):
        for name in activity_type_names:
            OBSERVATION_MAPPERS[name] = fn
        return fn
    return decorator
 
def _base_fields(activity: dict) -> dict:
    """Universal fields every observation gets, regardless of type.
 
    These are the safe defaults for an unmapped/operational activity.
    A mapper overrides whichever of these it can do better.
    """

    return dict(

        instrument_id=INSTRUMENT_UUID,
        external_observation_id=str(activity["id"]),
        date_range=DateRange(
            begin=datetime.fromisoformat(activity["start_time"]),
            end=datetime.fromisoformat(activity["end_time"]),
        ),
        status=ObservationStatus.PLANNED,
        type=ObservationType.TIMING,            # safest default; mappers override
        object_name="UNKNOWN",
        description=activity["activity_type_name"],
        bandpass=null_bandpass(),               # mappers override for real EM obs

    )

def across_specific_fields(data: dict) -> dict:
 
    return dict(
        pointing_position=Coordinate(ra=data["ra"], dec=data["dec"]),
        object_name=data["targetName"],
        description=data["description"]
    )

"""
Optional ACROSS fields:
    pointing_position
    pointing_angle
    exposure_time
    reason
    description
    proposal_reference
    object_position
    depth
    t_resolution
    em_res_power
    o_ucd
    pol_states
    pol_xel
    category
    priority
    tracking_type
    created_on
    created_by_id
    footprint
"""

@maps("ExampleActivityType")   # PlanDev plan activity name
def _example_activity_type(activity: dict) -> dict:

    activity_attributes = activity["attributes"]   # attributes object is activity-specific

    new_fields = dict(
        # Fields to be added or overwritten. For example:
        # exposure_time=activity_attributes["arguments"]["exposure_time"]
        # Values will likely need to be converted to the correct type first,
        # using arg() or arg_num()
    )

    return new_fields

@maps("ImageTarget")
def _imaging(activity: dict) -> dict:

    a = activity["attributes"]
    data = a["arguments"]
    fields = across_specific_fields(data)
 
    fields.update(
        type=ObservationType.IMAGING,
        exposure_time=data["exposure"],
        bandpass=Bandpass(EnergyBandpass(
            unit=EnergyUnit.KEV,
            min=data["energyMinKev"],
            max=data["energyMaxKev"]))
    )

    return fields

@maps("TimeTarget")
def _timing(activity: dict) -> dict:

    a = activity["attributes"]
    data = a["arguments"]
    fields = across_specific_fields(data)
 
    fields.update(
        type=ObservationType.TIMING,
        exposure_time=data["exposure"],
        bandpass=Bandpass(EnergyBandpass(
            unit=EnergyUnit.KEV,
            min=data["energyMinKev"],
            max=data["energyMaxKev"])),
        t_resolution=data["tResolution"]  # specific to timing
    )

    return fields

@maps("ObserveSpectrum")
def _observespectrum(activity: dict) -> dict:

    a = activity["attributes"]
    data = a["arguments"]
    fields = across_specific_fields(data)
 
    fields.update(
        type=ObservationType.SPECTROSCOPY,
        exposure_time=data["exposure"],
        bandpass=Bandpass(EnergyBandpass(
            unit=EnergyUnit.KEV,
            min=data["energyMinKev"],
            max=data["energyMaxKev"])),
        em_res_power=data["emResPower"]  # specific to spectroscopy
    )

    return fields

@maps("Slew")
def _slew(activity: dict) -> dict:

    a = activity["attributes"]
    data = a["arguments"]
    fields = across_specific_fields(data)
 
    fields.update(
        type=ObservationType.SLEW,
        pointing_angle=data["pointingAngle"]
    )

    return fields

## Add activity types here


# ---------------------------------------------------------------------------
# -- Schedule Assembly
# ---------------------------------------------------------------------------


def create_observation(activity: dict) -> ObservationCreate:

    fields = _base_fields(activity)
    mapper = OBSERVATION_MAPPERS.get(activity["activity_type_name"])

    if mapper is not None:
        fields.update(mapper(activity))
    else:
        UNMAPPED_TYPES.add(activity["activity_type_name"])

    return ObservationCreate(**fields)

def build_observations(activities: list) -> list:
    return [create_observation(a) for a in activities]

def create_schedule(sim: dict, plan_id: int) -> ScheduleCreate:

    activities = sim["simulation_datasets"][0]["simulated_activities"]

    if ALLOWED_ACTIVITY_TYPES:
        activities = [
            a for a in activities
            if a["activity_type_name"] in ALLOWED_ACTIVITY_TYPES
        ]
 
    schedule = ScheduleCreate(

        telescope_id=TELESCOPE_UUID,
        name=sim["plan"]["name"],
        date_range=DateRange(
            begin=datetime.fromisoformat(sim["simulation_start_time"]),
            end=datetime.fromisoformat(sim["simulation_end_time"]),
        ),
        status=ScheduleStatus.PLANNED,
        fidelity=ScheduleFidelity.LOW,
        external_id=str(plan_id),
        observations=build_observations(activities),

    )
 
    if UNMAPPED_TYPES:
        print("No mapper for these activity types (used placeholders):", sorted(UNMAPPED_TYPES))

    return schedule