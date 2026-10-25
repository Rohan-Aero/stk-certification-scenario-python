# STK Certification Scenario: Python-Automated Mission Analysis

An [Ansys/AGI STK](https://www.ansys.com/products/missions/ansys-stk) 13 scenario for a flight over Peru's Ica / Paracas region, built end to end from Python. A script drives the running STK desktop application through the `agi.stk13` Python API and Connect commands. It builds the scenario, then reads every object back and checks it against the saved files.

The scenario compares how soon, and for how long, an aircraft-mounted camera and a satellite-mounted camera can see the city of Ica.

## Scenario at a glance

| Item | Setting |
|---|---|
| Scenario | `STK_Cert_RohanPatel_V13`, STK 13.1.0.739 |
| Time window | 28 Oct 2011 18:54:00 to 23:54:00 UTC (5 h) |
| Terrain server | Off for analysis (see [Known limitation](#known-limitation)) |
| **Places** | `Ica`, `Paracas` |
| **Area target** | `Runway`: 4 vertices, 2° minimum elevation constraint |
| **Aircraft** | `CertAircraft`: Great Arc, waypoints Runway centroid, Paracas, Ica, Runway. 14 km altitude, 350 nm/hr, 1 km turn radius, `uav.glb` model, Coordinated Turn attitude, white route (width 3) |
| **Aircraft sensor** | `AC_Camera`: rectangular, 100° x 100° |
| **Satellite** | `CertSatellite`: TwoBody, 15° inclination, `cubesat_3u.glb` model |
| **Satellite sensor** | `Sat_Camera`: Simple Conic, 60° full angle (30° half angle) |

The aircraft altitude was chosen with an altitude sweep. At STK's default 10.668 km the aircraft kept runway access for only 81.8% of the flight. At 14 km it is one unbroken access interval covering the whole flight.

## Results: aircraft camera vs. satellite camera

Access to Ica, computed by STK (full output in [`STK_Cert_RohanPatel_V13/T10_AccessComparison.txt`](STK_Cert_RohanPatel_V13/T10_AccessComparison.txt)):

| | First access | Longest single interval | Total access |
|---|---|---|---|
| Aircraft camera (`AC_Camera`) | 19:17:01.484 | 81.519 s | 150.264 s |
| Satellite camera (`Sat_Camera`) | 19:59:17.795 | 47.800 s | 90.375 s |

The aircraft camera reaches Ica first and has the longest single access and the longest total access. Its access splits in two because the banked U-turn at Ica briefly tilts the nadir-pointing camera away from the city.

## Deliverables

All in [`STK_Cert_RohanPatel_V13/`](STK_Cert_RohanPatel_V13/) (also bundled as `STK_Cert_RohanPatel_V13.zip`):

| File | What it is |
|---|---|
| `STK_Cert_RohanPatel_V13.sc` and the object files (`.ac`, `.sa`, `.sn`, `.plc`, `.at`) | The saved STK scenario and its objects |
| `T1_QuakeRegion_view.png` | Stored 3D view of the quake region |
| `Ica_LatLon.rst` | Quick report of Ica's latitude and longitude |
| `FlightSummary.csv` / `.rst` | Aircraft time, lat, lon, alt, azimuth, elevation, velocity |
| `AircraftView.wmv` | About 12 s top-down flyover of Ica |
| `SatView.bmp` | Satellite model and camera cone at the first Sat_Camera to Ica access |
| `T10_AccessComparison.txt` | The comparison above |

## Repository layout

```
.
├── stk_common.py            # attach to / start STK, Connect wrapper, task tracker, logging
├── environment_check.py     # prints OS, Python, STK path and license report
├── scenario_setup.py        # scenario, runway, places, stored view, timeline, quick report
├── aircraft_setup.py        # aircraft, waypoints, style, camera, altitude sweep, video, CSV export
├── satellite_setup.py       # satellite, camera, first access, SatView.bmp, report, comparison
├── deliverable_validation.py# checks the SAVED files and the live STK against the spec
├── tracker.json             # per-task status written by the scripts
├── stk_run.log              # log of every Connect command issued
├── STK_Cert_RohanPatel_V13/ # scenario folder the scripts write to and validate against
├── backups/                 # timestamped snapshots taken between phases
└── *.sc *.ac *.sa ...       # scenario and object files also present at the repo root
```

## Running it

**Requirements:** Windows, STK 13.1 with a license (Pro was used), Python 3.12.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install "C:\Program Files\AGI\STK_ODTK 13\bin\AgPythonAPI\agi_stk13-13.1.0-py3-none-any.whl"
```

STK's install path and style/model paths are hardcoded to `C:\Program Files\AGI\STK_ODTK 13`. Adjust them if yours differs.

Each script attaches to the single running STK instance, or starts one. It refuses to run if more than one STK is open or if a different scenario is loaded.

```bash
python environment_check.py                  # what can this machine do?
python scenario_setup.py                     # scenario, 5 h window, terrain
python scenario_setup.py runway              # also: places | t1 | t2 | t3
python aircraft_setup.py aircraft t4 t6      # also: sweep | fine
python satellite_setup.py sat t8             # also: access | snap | report | compare
python deliverable_validation.py             # PASS/FAIL per requirement
```

## Verification

Every task is tracked in `tracker.json` with a status (`Not started`, `In progress`, `Needs verification`, `Verified`, `Blocked`). `deliverable_validation.py` re-reads the saved scenario files, and the live STK session if one is running, and sets the final status. Examples of what it checks: runway vertices and elevation angle, place coordinates, the Ica lighting timeline row, the `FlightSummary.csv` fields, and the 60° sensor cone.

All tasks are `Verified` except one, covered next.

### Known limitation

**Terrain** is marked `Needs verification`. The API setter for *Use terrain server for analysis* was refused in this build. The value reads back as off through the API and in the saved `.sc`, but the GUI checkbox was never observed directly.
