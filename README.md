# PASS – PlanDev-ACROSS Schedule Sender

A desktop application that bridges observation planning and scheduling systems by enabling users to send schedules from **PlanDev** (a planning and simulation system) to **ACROSS** (a scheduling and observation management system).

## Purpose

PASS solves the workflow gap between observation planning and execution by providing an intuitive graphical interface to:

1. **Select observation targets** – Choose a telescope and its corresponding instrument from your observatory infrastructure
2. **Load simulation data** – Retrieve pre-planned observation schedules and activity data from PlanDev
3. **Configure schedule parameters** – Adjust fidelity levels and observation status before sending
4. **Filter activities** – Select which activity types to include in the final schedule
5. **Submit to ACROSS** – Post the complete schedule to ACROSS for operational execution

This tool is essential for multi-mission observatory environments where observation plans must be simulated and validated in a planning system before being transmitted to the live scheduling system.

## Architecture

### System Integration

```
┌─────────────────────────────────────────────────────────────┐
│                    Desktop UI (Tkinter)                     │
│              (ScheduleUI – schedule_ui.py)                  │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
    ┌────▼────┐  ┌──────▼──────┐  ┌────▼─────┐
    │ PlanDev │  │ Hasura API  │  │  ACROSS  │
    │  Data   │  │ (GraphQL)   │  │  Client  │
    │ Loading │  │ Simulation  │  │  (REST)  │
    └─────────┘  └─────────────┘  └──────────┘
```

### Core Modules

- **schedule_ui.py** – Tkinter-based user interface with dropdown menus for telescope/instrument/plan selection and observation activity filtering
- **across_sdk.py** – Observation mapping layer that converts PlanDev activity data into ACROSS-compatible observation objects
  - Handles multiple observation types (Imaging, Timing, Spectroscopy, Slew)
  - Provides a pluggable mapper registry for adding new activity types
  - Dynamically fetches instrument configurations (bandpass, resolution) from Hasura resources
  - Queries telescope pointing resources at precise observation start times
- **across_data.py** – Data fetching from PlanDev's REST API for telescopes, instruments, plans, and activity metadata
- **hasura_client.py** – GraphQL client for fetching detailed simulation datasets including simulated activities and resource values at specific time offsets
  - `get_resource_at_time()` – Queries telescope pointing (RA/Dec) at observation start times
  - `get_constant_resources()` – Fetches instrument configuration parameters dynamically
  - `offset_to_interval()` – Converts PlanDev offset strings to GraphQL interval format
- **config.py** – Environment configuration management for API credentials and endpoints

## Installation

### Prerequisites

- Python 3.9+
- `tkinter` (usually bundled with Python; on Linux, install via your package manager)
- The `across-client` SDK for ACROSS API integration

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/remy-rabideau/PASS.git
   cd PASS
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   Copy `.env.template` to `.env` and fill in your credentials:
   ```bash
   cp .env.template .env
   ```

   Required variables:
   - `HASURA_URL` – GraphQL endpoint for simulation data
   - `HASURA_ADMIN_SECRET` – Hasura admin authentication token
   - `ACROSS_CLIENT_ID` – ACROSS API client identifier
   - `ACROSS_CLIENT_SECRET` – ACROSS API client secret

## Usage

### Running the Application

```bash
python main.py
```

The UI will launch with the following workflow:

1. **Select Telescope** – Choose from available observatories (loads automatically)
2. **Select Instrument** – Pick an instrument attached to the selected telescope
3. **Select Plan** – Choose an observation plan from PlanDev (filtered by telescope + instrument)
4. **Configure Observations**
   - **Fidelity** – Set observation fidelity (LOW, MEDIUM, HIGH)
   - **Status** – Set observation status (PLANNED, COMMITTED, APPROVED)
   - **Activity Types** – Filter which activity types to include (e.g., exclude slews, calibrations)
5. **Send to ACROSS** – Submit the schedule; the UI displays the new ACROSS schedule ID on success

### Example Workflow

```
Load telescopes… ✓
Select "Chandra" telescope
  → Instruments populate: "ACIS-I", "ACIS-S", "HRC", "LETG"
Select "ACIS-I" instrument
  → Load plans…
Select "NGC-1234-Survey" plan
  → Load activity types: "ImageTarget", "TimeTarget", "Slew"
Uncheck "Slew" to exclude telescope slew activities
Click "Send to ACROSS"
  → Success! ACROSS Schedule ID: 12345abc
```

## Key Features

### Extensible Mapper System

Add support for new PlanDev activity types by registering a mapper in `across_sdk.py`:

```python
@maps("MyNewActivityType")
def _my_new_activity_type(activity: dict, simulation_dataset_id: int) -> dict:
    """Convert PlanDev activity to ACROSS observation fields."""
    data = activity["attributes"]["arguments"]
    
    # Get telescope pointing and instrument config at observation start time
    fields = across_specific_fields(data, simulation_dataset_id, activity["start_offset"])
    
    fields.update(
        type=ObservationType.IMAGING,
        # ... additional ACROSS fields
    )
    
    return fields
```

### Dynamic Resource Queries

PASS queries Hasura resources to fetch real-time telescope pointing and instrument configurations:

- **Telescope Pointing** – RA/Dec coordinates are queried at each observation's start time (with 1 microsecond offset to ensure slew completion)
- **Instrument Configuration** – Bandpass parameters (type, unit, min, max), time resolution, and EM resolution power are fetched from simulation resources instead of hardcoded values
- **Offset Conversion** – PlanDev offset strings (e.g., "1 day 06:10:15.963036") are converted to GraphQL interval format for precise resource queries

### Activity Type Discovery

Unmapped activity types are collected during processing and logged to stdout, enabling incremental mapper implementation:

```
No mapper for these activity types (used placeholders): ["NewActivityType", "UnknownOp"]
```

## Data Flow

### Schedule Creation Process

1. User selects telescope/instrument in UI
2. PlanDev API returns available plans
3. User selects plan; Hasura GraphQL fetches simulation data
4. Simulated activities are iterated and converted to ACROSS Observations via mapper registry
5. ScheduleCreate object is assembled with:
   - Telescope UUID
   - Fidelity and status from UI selections
   - Filtered observations based on activity type selection
6. ACROSS Client posts schedule; returns new schedule ID

### Data Transformation

```
PlanDev Activity
    ↓
_base_fields() → safe defaults (ObservationStatus.PLANNED, ObservationType.TIMING, etc.)
    ↓
across_specific_fields() → queries Hasura for:
    - Telescope pointing (RA/Dec) at observation start time
    - Instrument configuration (bandpass type/unit/range, time resolution, EM resolution)
    ↓
Activity-type mapper (e.g., _imaging(), _timing()) → enriched fields
    ↓
ObservationCreate (ACROSS SDK model)
    ↓
ScheduleCreate (collection of observations)
    ↓
Client.schedule.post() → ACROSS REST API
    ↓
ACROSS Schedule ID (returned to user)
```

## Environment Configuration

Create a `.env` file (or use `.env.template` as a template):

```env
# Hasura GraphQL endpoint for simulation data
HASURA_URL=https://hasura.example.com/graphql

# Hasura admin token for API authentication
HASURA_ADMIN_SECRET=your-admin-secret

# ACROSS API credentials
ACROSS_CLIENT_ID=your-client-id
ACROSS_CLIENT_SECRET=your-client-secret
```

## Dependencies

- **across-client** – Official ACROSS SDK for schedule submission and data models
- **tkinter** – Python's standard GUI toolkit (included with Python; install separately on Linux)
- **python-dotenv** – Environment variable management
- **requests** (via across-client) – HTTP client for REST API calls

## Development

### Adding a New Activity Type Mapper

1. Inspect the PlanDev activity structure (printed to stdout on first encounter)
2. Create a mapper function in `across_sdk.py`:
   ```python
   @maps("MyActivityType")
   def _my_activity(activity: dict, simulation_dataset_id: int) -> dict:
       data = activity["attributes"]["arguments"]
       
       # Get dynamic telescope pointing and instrument config
       fields = across_specific_fields(data, simulation_dataset_id, activity["start_offset"])
       
       fields.update(
           type=ObservationType.IMAGING,
           # ... more fields
       )
       
       return fields
   ```
3. Test by running PASS and selecting a plan containing the activity type
4. Verify the observation appears correctly in ACROSS

### Debugging

- Check UI status messages for API errors
- Review stdout for unmapped activity type warnings
- Enable verbose logging by modifying `schedule_ui.py` or `hasura_client.py`
- Test individual components (e.g., `across_data.get_telescopes()`) in a Python REPL

## License

MIT License – See LICENSE file for details.

## Troubleshooting

### "Failed to load telescopes"
- Verify `HASURA_URL` and `HASURA_ADMIN_SECRET` are correct
- Check network connectivity to Hasura endpoint
- Ensure authentication token is valid and has admin privileges

### "This telescope has no instruments"
- The selected telescope may not have instruments registered in PlanDev
- Contact your observatory administrator to verify telescope/instrument configuration

### "Send failed" on ACROSS submission
- Verify `ACROSS_CLIENT_ID` and `ACROSS_CLIENT_SECRET` are correct
- Ensure the ACROSS API endpoint is accessible
- Check for activity type mapper warnings in the console

## Contributing

Contributions are welcome! To extend PASS:

1. Add mapper functions for new PlanDev activity types
2. Enhance error handling and user feedback
3. Improve the UI layout or add advanced features
4. Optimize API calls or data fetching

---

**Questions or Issues?** Open an issue on GitHub or contact the development team.
