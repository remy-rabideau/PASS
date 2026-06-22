# Canonical `ObserveTarget` activity contract

The model and the integration agree on **one** activity type, `ObserveTarget`.
Both directions (PlanDev → ACROSS export, and ACROSS → PlanDev import) use it, so
the round trip is symmetric and lossless. This replaces the four separate
`ImageTarget` / `TimeTarget` / `ObserveSpectrum` / `Slew` mappers.

## Why one type
- ACROSS already has a single `ObservationType` enum (`imaging | timing |
  spectroscopy | slew`). The activity's `observationType` argument maps straight
  to it — no need for four PlanDev activity types.
- The importer can write any ACROSS observation back as one uniform activity.
- One activity to define in the mission model JAR instead of four.

## Arguments (PlanDev activity `arguments` ⇄ ACROSS `ObservationCreate`)

| argument           | type / values                                   | ACROSS field            | notes |
|--------------------|-------------------------------------------------|-------------------------|-------|
| `observationType`  | `imaging`\|`timing`\|`spectroscopy`\|`slew`      | `type`                  | required |
| `instrument`       | logical name, e.g. `XRayImager`                 | `instrument_id`         | resolved name→UUID by integration; falls back to UI-selected instrument |
| `targetName`       | string                                          | `object_name`           | |
| `ra`, `dec`        | degrees                                         | `pointing_position`     | |
| `exposure`         | seconds                                         | `exposure_time`         | omitted for `slew` |
| `bandpassType`     | `energy`\|`wavelength`\|`frequency`             | `bandpass` (type)       | default `energy` |
| `bandMin`,`bandMax`| number (keV / nm / GHz per `bandpassType`)      | `bandpass` (min,max)    | null → open bandpass |
| `tResolution`      | seconds                                         | `t_resolution`          | `timing` only |
| `emResPower`       | number                                          | `em_res_power`          | `spectroscopy` only |
| `pointingAngle`    | degrees                                         | `pointing_angle`        | `slew` only |
| `acrossId`         | string                                          | `external_observation_id` | set on import for idempotent / lossless re-export |

## Forward (export)
`create_observation` reads `observationType` to pick the ACROSS type, resolves
`instrument` → UUID, builds the bandpass from `bandpassType`/`bandMin`/`bandMax`,
and fills the kind-specific field. One activity → one observation. (Per-instrument
fan-out is done in the *model*: one science intent spawns one `ObserveTarget`
child per instrument.)

## Inverse (import)
`observation_to_activity` fills every argument above from an ACROSS observation,
including `acrossId`, so a re-export targets the same observation. Known v1 gap:
`instrument` is left unset on import (ACROSS returns a UUID, not the model's
logical name); resolving UUID→name needs the telescope context.

## Known follow-ups
- Filter by observation kind (e.g. exclude `slew`) instead of by activity-type name.
- Round-trip the bandpass and instrument name on import.
