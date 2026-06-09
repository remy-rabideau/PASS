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
from across.sdk.v1.models.frequency_bandpass import FrequencyBandpass
from across.sdk.v1.models.wavelength_bandpass import WavelengthBandpass
from across.sdk.v1.models.energy_unit import EnergyUnit
from across.sdk.v1.models.frequency_unit import FrequencyUnit
from across.sdk.v1.models.wavelength_unit import WavelengthUnit
from across.sdk.v1.models.coordinate import Coordinate

from hasura_client import get_resource_at_time, get_constant_resources

# values set by schedule_ui
TELESCOPE_UUID = ""
INSTRUMENT_UUID = ""
INSTRUMENT_NAME = ""
ALLOWED_ACTIVITY_TYPES = []


# ---------------------------------------------------------------------------
# -- Helpers
# ---------------------------------------------------------------------------


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
        type=ObservationType.TIMING,  # safest default; mappers override
        object_name="UNKNOWN",
        description=activity["activity_type_name"],
        bandpass=null_bandpass(),  # mappers override for real EM obs
    )

def across_specific_fields(data: dict, simulation_dataset_id: int, offset: str):

    instr_name = data["instrumentName"]
    ra = get_resource_at_time(simulation_dataset_id, "telescope.pointingRa", offset)
    dec = get_resource_at_time(simulation_dataset_id, "telescope.pointingDec", offset)
    const_res = get_constant_resources(simulation_dataset_id, "instrument." + instr_name)

    bandpassType = None
    bandpassUnit = None
    bandpassMin = None
    bandpassMax = None
    tRes = None
    emRes = None

    for res in const_res:
        name = res["name"]
        value = res["dynamics"]
        
        if "bandpassType" in name:
            bandpassType = value
        elif "bandpassUnit" in name:
            bandpassUnit = value
        elif "bandMin" in name:
            bandpassMin = value
        elif "bandMax" in name:
            bandpassMax = value
        elif "tResolution" in name:
            tRes = value
        elif "emResPower" in name:
            emRes = value

    bandpass = null_bandpass()
    
    if bandpassType:
        match bandpassType:
            case "ENERGY":
                bandpass = Bandpass(EnergyBandpass(unit=EnergyUnit(bandpassUnit), min=bandpassMin, max=bandpassMax))
            case "FREQUENCY":
                bandpass = Bandpass(FrequencyBandpass(unit=FrequencyUnit(bandpassUnit), min=bandpassMin, max=bandpassMax))
            case "WAVELENGTH":
                bandpass = Bandpass(WavelengthBandpass(unit=WavelengthUnit(bandpassUnit), min=bandpassMin, max=bandpassMax))
            case _:
                bandpass = null_bandpass()

    return dict(
        pointing_position=Coordinate(ra=ra, dec=dec),
        object_name=data["targetName"],
        description=data["description"],
        exposure_time=data["exposure"],
        bandpass=bandpass,
        t_resolution=tRes,
        em_res_power=emRes,
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


@maps("ExampleActivityType")  # PlanDev plan activity name
def _example_activity_type(activity: dict, simulation_dataset_id: int) -> dict:

    # activity_attributes = activity[
    #     "attributes"
    # ]  # attributes object is activity-specific

    new_fields = dict(
        # Fields to be added or overwritten. For example:
        # exposure_time=activity_attributes["arguments"]["exposure_time"]
        # Values will likely need to be converted to the correct type first,
        # using arg() or arg_num()
    )

    return new_fields


@maps("ImageTarget")
def _imaging(activity: dict, simulation_dataset_id: int) -> dict:

    data = activity["attributes"]["arguments"]
    fields = across_specific_fields(
        data, simulation_dataset_id, activity["start_offset"]
    )

    fields.update(
        type=ObservationType.IMAGING,
    )

    return fields


@maps("TimeTarget")
def _timing(activity: dict, simulation_dataset_id: int) -> dict:

    data = activity["attributes"]["arguments"]
    fields = across_specific_fields(
        data, simulation_dataset_id, activity["start_offset"]
    )

    fields.update(
        type=ObservationType.TIMING,
    )

    return fields


@maps("ObserveSpectrum")
def _observespectrum(activity: dict, simulation_dataset_id: int) -> dict:

    data = activity["attributes"]["arguments"]
    fields = across_specific_fields(
        data, simulation_dataset_id, activity["start_offset"]
    )

    fields.update(
        type=ObservationType.SPECTROSCOPY,
    )

    return fields


@maps("Slew")
def _slew(activity: dict, simulation_dataset_id: int) -> dict:

    data = activity["attributes"]["arguments"]

    ra = data["ra"]
    dec = data["dec"]

    fields = dict(
        type=ObservationType.SLEW,
        pointing_position=Coordinate(ra=ra, dec=dec),
        pointing_angle=data["pointingAngle"],
    )

    return fields


## Add activity types here


# ---------------------------------------------------------------------------
# -- Schedule Assembly
# ---------------------------------------------------------------------------


def create_observation(activity: dict, simulation_dataset_id: int) -> ObservationCreate:

    print(activity)
    if INSTRUMENT_NAME != activity["attributes"]["arguments"]["instrumentName"]:
        raise ValueError(f"Activity {activity['activity_type_name']} is not for {INSTRUMENT_NAME}")

    fields = _base_fields(activity)
    mapper = OBSERVATION_MAPPERS.get(activity["activity_type_name"])

    if mapper is not None:
        fields.update(mapper(activity, simulation_dataset_id))
    else:
        UNMAPPED_TYPES.add(activity["activity_type_name"])

    return ObservationCreate(**fields)


def build_observations(activities: list, simulation_dataset_id: int) -> list:
    return [create_observation(a, simulation_dataset_id) for a in activities]


def create_schedule(sim: dict, plan_id: int) -> ScheduleCreate:

    activities = sim["simulation_datasets"][0]["simulated_activities"]
    simulation_dataset_id = sim["simulation_datasets"][0]["id"]

    if ALLOWED_ACTIVITY_TYPES:
        activities = [
            a for a in activities if a["activity_type_name"] in ALLOWED_ACTIVITY_TYPES
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
        observations=build_observations(activities, simulation_dataset_id),
    )

    if UNMAPPED_TYPES:
        print(
            "No mapper for these activity types (used placeholders):",
            sorted(UNMAPPED_TYPES),
        )

    return schedule
