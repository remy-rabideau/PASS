# Archived: ACROSS events overlay

Pulls ACROSS events (broker alerts, or observations as a fallback) and overlays
them on a PlanDev plan as external events. Archived to keep the active app focused
on export / import / visibility. Nothing here runs unless restored.

## Files
- external_events.py  — the overlay engine (read ACROSS -> upload to gateway -> link to plan)
- alerts.html         — the Flask page

## To restore
1. Move external_events.py to the repo root and alerts.html back to templates/.
2. In config.py add:  GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:9000")
3. In app.py re-add:  from external_events import sync_alerts   + the /alerts route.
4. (optional) re-register the PlanDev extension row + its extension_roles.
