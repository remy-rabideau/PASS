# PlanDev ⇄ ACROSS Integration

A small Flask service that connects a local **PlanDev** (NASA Aerie) instance to
**ACROSS** (NASA's Astrophysics Cross-Observatory Science Support API), in both
directions. It lets a planner send a simulated plan to ACROSS, pull real ACROSS
data back into a plan, and overlay external ACROSS events on a plan's timeline.

## What it does

| Flow | Direction | Entry point |
|------|-----------|-------------|
| **Export** | plan's simulated activities → ACROSS schedule | `/` |
| **Import** | ACROSS observations → plan activities | `/import` |
| **Alerts overlay** | ACROSS events → plan external events (timeline) | `/alerts`, extension |
| **Visibility** | resolve a target, ask ACROSS when it is observable | `/visibility` |

## Architecture

Three systems, each reached through its own interface. Flask runs on the host;
PlanDev runs in Docker.

```
 HOST                                   DOCKER (PlanDev)                  CLOUD
  Flask :5000 ── GraphQL ─────────────► Hasura  :8080 ─► Postgres :5432
       │  (this service)                Gateway :9000 ─► (all data)
       │         ── multipart upload ─► (JARs, external sources)
       │                                Aerie UI :80  ─► reads DB via Hasura
       ▼  HTTPS
  ACROSS REST  api.across.sciencecloud.nasa.gov/v1
```

- **ACROSS REST** — the science API. Reads need no credentials; the export POST
  needs `ACROSS_CLIENT_ID`/`SECRET`.
- **Hasura** (`:8080`) — PlanDev's GraphQL API over Postgres (read plans/sims,
  write activities, link derivation groups).
- **Gateway** (`:9000`) — PlanDev's upload/auth service (model JARs, external
  sources). Local PlanDev runs `AUTH_TYPE=none`, so any login mints a token.

## Modules & functions

| Module | Function | Role in the pipeline |
|--------|----------|----------------------|
| `config.py` | — | Loads `.env` (Hasura, gateway, ACROSS creds). |
| `plandev.py` | `query` | One GraphQL request helper (admin secret). |
| | `get_simulation` | Read a plan's latest simulation + simulated activities. |
| | `insert_activity` | Write one activity directive into a plan. |
| | `get_plans`, `get_activity_types` | PlanDev plans / a plan's activity types. |
| `across_client.py` | `get_telescopes` | ACROSS telescopes + instruments (UUIDs). |
| | `get_nearby_observations` | ACROSS cone search (`GET /observation/`). |
| | `resolve_object` | Name → RA/Dec (`GET /tools/resolve-object/`). |
| | `get_visibility_windows` | When an instrument can see a target. |
| `mappers.py` | `build_bandpass` | bandpassType + min/max → ACROSS Bandpass. |
| | `_resolve_instrument` | Instrument name → ACROSS UUID. |
| | `_observe_target`, `create_observation` | One `ObserveTarget` activity → one ACROSS observation. |
| | `build_observations`, `create_schedule` | Activities → a `ScheduleCreate`. |
| | `observation_to_activity` | Inverse: one ACROSS observation → one `ObserveTarget`. |
| `external_events.py` | `get_broker_events` | ACROSS multi-messenger alerts (`GET /broker-event/`). |
| | `get_observation_events` | Other observatories' observations as events. |
| | `sample_events` | Labelled fallback when ACROSS is unreachable. |
| | `_gateway_token` | Mint a gateway token. |
| | `_build_source` | Assemble the external-source document (header + events). |
| | `_upload_types`, `_upload_source` | Write event types / source to the gateway. |
| | `_plan_window`, `_link_to_plan` | Plan time range / link group to plan. |
| | `sync_alerts` | Orchestrates the overlay (fetch → upload → link). |
| `app.py` | `index`, `import_observations`, `visibility`, `alerts` | The four UI pages. |
| | `extension_sync_alerts` | JSON endpoint for the PlanDev UI extension button. |

## The pipelines

**Export** (`/`): `get_simulation` reads the plan's simulated `ObserveTarget`s →
`create_schedule` maps each to an ACROSS observation (type, instrument UUID,
pointing, bandpass, exposure) → `Client.schedule.post` → ACROSS.

**Import** (`/import`): `get_nearby_observations` cone-searches ACROSS →
`observation_to_activity` maps each → `insert_activity` writes it into the plan.

**Alerts overlay** (`/alerts` or the extension): `sync_alerts` pulls ACROSS
events (broker alerts first, else real observations), uploads them as external
events through the gateway, and links their derivation group to the plan, so
they appear on the timeline.

**Visibility** (`/visibility`): `resolve_object` → `get_visibility_windows` +
`get_nearby_observations` for context.

## The activity

Both directions use a single PlanDev activity, **`ObserveTarget`**, with an
`observationType` argument (`imaging | timing | spectroscopy | slew`). Its
arguments and their ACROSS mapping are the contract in
[`OBSERVE_TARGET_CONTRACT.md`](OBSERVE_TARGET_CONTRACT.md). The mission model JAR
(project `observatory-model`) defines exactly this activity.

## Setup

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # then edit
```

```ini
HASURA_URL=http://localhost:8080/v1/graphql
HASURA_ADMIN_SECRET=aerie
GATEWAY_URL=http://localhost:9000
ACROSS_CLIENT_ID=        # only for the live export POST
ACROSS_CLIENT_SECRET=
```

## Run

```sh
.venv/bin/python -m pytest -q     # tests
.venv/bin/python app.py           # UI -> http://localhost:5000
```

Everything can also be driven by API: the gateway uploads model JARs and external
sources, and Hasura handles plans/activities — `sync_alerts` already does the
overlay end to end this way.

## Status

- **Import, alerts overlay, visibility** — fully working (no ACROSS credentials
  needed; they use ACROSS reads + PlanDev writes).
- **Export** — fully mapped and verified; the final `POST /schedule` is the only
  step that needs ACROSS credentials. Add `ACROSS_CLIENT_ID`/`SECRET` once you
  have access and export completes end to end.
