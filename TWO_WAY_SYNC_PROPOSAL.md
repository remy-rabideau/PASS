# Two-Way Sync: PlanDev ⇄ ACROSS — Feasibility & Proposal

## What exists today (one-way)
PlanDev plan → convert activities → POST schedule to ACROSS. Verified working
against live ACROSS. This is *forwarding*: a planner already decided everything,
PASS just delivers it.

## The more significant experiment: a real round trip
Add the reverse direction — pull what is **already scheduled in ACROSS** and bring
it into PlanDev — so a planner can see the full sky context and plan around it.
This is what ACROSS is *for* (cross-observatory coordination), not just delivery.

## Feasibility — both directions confirmed against real systems

### ACROSS → read (no credentials needed; live now)
- `GET /observation/` — 892,141 real observations, filterable by:
  sky position (`cone_search_ra/dec/radius`), time (`date_range_begin/end`),
  instrument, telescope, bandpass, type, status.
- `GET /schedule/` — 1,824 real schedules.
- Observation fields include: `pointing_position`, `date_range`, `object_name`,
  `instrument_id`, `bandpass`, `type`, `status`.

### PlanDev → write (confirmed; needs the user's PlanDev session)
- Mutation `insert_activity_directive_one` exists and is used across the JPL projects.
- Shape (from OPERATING_GUIDE.md):
  ```
  insert_activity_directive_one(object: {
    plan_id, type, arguments: {...}, start_offset, name
  }) { id }
  ```
- So an ACROSS observation can become a PlanDev activity directive: map
  pointing/time/instrument → arguments + start_offset relative to plan start.

## The meaningful demo (round trip)
1. Pick a PlanDev plan + a sky region / time window.
2. PASS queries live ACROSS: "what is already being observed here?" (cone search).
3. Show those real observations alongside the plan.
4. Optionally write selected ACROSS observations back into the plan as activity
   directives (so PlanDev's scheduler accounts for them).
5. Re-simulate; the plan now reflects real cross-observatory context.

## Why this is more significant than one-way
- Uses ACROSS's actual purpose (coordination), not just as a sink.
- Exercises the open ACROSS read API (no creds) → fully demoable now.
- The write-back is the genuinely new capability the current code never had
  (it only ever *reads* PlanDev; this *writes* to it).

## Open questions before building
- Inverse mapping: which ACROSS observation fields → which PlanDev activity
  arguments? Depends on the target mission model's activity types.
- Write auth: `insert_activity_directive_one` runs against the user's local
  PlanDev (Hasura) — same secret already in `.env`. No ACROSS creds needed for
  the read+write-back path.
- Scope of v1: read-and-display only (zero write, fully safe) vs.
  read-and-write-back (creates activities in the plan).
