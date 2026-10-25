"""Part 2: CertAircraft (Great Arc), waypoints, route style, uav.glb, Coordinated Turn, AC_Camera. Usage: aircraft_setup.py <step>..."""
import datetime as dt
import math
import sys

from agi.stk13 import stkobjects as so
from agi.stk13.stkobjects import AgESTKObjectType as T, AgEVePropagatorType as P
from agi.stk13.utilities.colors import Colors

from scenario_setup import NAME, FOLDER, QUAKE_VIEW
from stk_common import get_app, connect, track, log

AC, CAM = "CertAircraft", "AC_Camera"
TURN_RADIUS_KM = 1.0
MODEL = r"STKData\VO\Models\Air\uav.glb"        # same relative style STK uses for its default aircraft.glb
FOV_FULL_DEG = 100.0                            # full angle; STK sensors take HALF angles
FINAL_ALT_KM = 14.0                             # sweep: 13.5 km = 99.4% access, 14 km = full single interval


def attach():
    app = get_app()                              # caller must keep `app` referenced (COM pointer dies on GC)
    sc = app.Root.CurrentScenario
    assert sc.InstanceName == NAME, "wrong scenario open"
    return app, app.Root, sc


def create_aircraft(sc):
    track("Aircraft", "In progress")
    if not sc.Children.Contains(T.eAircraft, AC):
        sc.Children.New(T.eAircraft, AC)
    ac = sc.Children.Item(AC)
    ac.SetRouteType(P.ePropagatorGreatArc)
    return ac


def set_waypoints(sc, ac, altitude_km=None):
    """Runway centroid -> Paracas -> Ica -> Runway. Altitude/speed default to STK's (10.668 km, 0.18 km/s) unless given."""
    track("Waypoints", "In progress")
    route = ac.Route
    alt = route.DefaultAltitude if altitude_km is None else altitude_km
    speed = route.DefaultRate
    rlat, rlon, _ = sc.Children.Item("Runway").Position.QueryPlanetodetic()          # area target centroid
    pts = [("Runway centroid", rlat, rlon)]
    for p in ("Paracas", "Ica"):
        la, lo, _ = sc.Children.Item(p).Position.QueryPlanetodetic()
        pts.append((p, la, lo))
    pts.append(("Runway", rlat, rlon))
    route.Waypoints.RemoveAll()
    for _, la, lo in pts:
        w = route.Waypoints.Add()
        w.Latitude, w.Longitude, w.Altitude, w.Speed, w.TurnRadius = la, lo, alt, speed, TURN_RADIUS_KM
    route.Propagate()
    return [n for n, _, _ in pts]


def style_aircraft(ac):
    track("Route style", "In progress")
    a = ac.Graphics.Attributes
    before = int(a.Line.Width)
    a.Color = Colors.White
    a.Line.Width = before + 1                                                      # one enum level thicker than STK default
    track("Model+Attitude", "In progress")
    ac.VO.Model.ModelType = so.AgEModelType.eModelFile
    ac.VO.Model.ModelData.Filename = MODEL
    ac.Attitude.Basic.SetProfileType(so.AgEVeProfile.eCoordinatedTurn)
    return before


def create_camera(ac):
    track("AC_Camera", "In progress")
    if not ac.Children.Contains(T.eSensor, CAM):
        ac.Children.New(T.eSensor, CAM)
    sn = ac.Children.Item(CAM)
    sn.SetPatternType(so.AgESnPattern.eSnRectangular)
    sn.Pattern.HorizontalHalfAngle = FOV_FULL_DEG / 2
    sn.Pattern.VerticalHalfAngle = FOV_FULL_DEG / 2
    return sn


STYLES = r"C:\Program Files\AGI\STK_ODTK 13\STKData\Styles\Aircraft"
FS_NAME = "FlightSummary"
# (source style, element Name in that style): the exercise's exact seven fields; STK's own element titles are kept. Time is forced to EpSec.
FS_FIELDS = [("LLA Position", "Time"), ("LLA Position", "LLA State-Fixed-Lat"), ("LLA Position", "LLA State-Fixed-Lon"),
             ("LLA Position", "LLA State-Fixed-Alt"), ("Velocity Heading", "Heading-Fixed-Azimuth"),
             ("Velocity Heading", "Heading-Fixed-Elevation"), ("Velocity Heading", "Heading-Fixed-Velocity")]
EPSEC_UNITS = "UseScenUnits\tNo\nBEGIN Units\n\t\tDateFormat\tEpochSeconds\nEND Units\n"   # form STK itself uses (e.g. Access Detailed.rst)


def make_flight_style():
    """Assemble a report style from elements of STK's own Aircraft styles (mixing providers in one line is how STK's Ephemeris-IFT-LLA works)."""
    import re
    src = {n: open(rf"{STYLES}\{n}.rst", encoding="utf-8").read().replace("\r", "") for n in {f[0] for f in FS_FIELDS}}
    blocks = []
    for style, ename in FS_FIELDS:
        b = next(m for m in re.findall(r"BEGIN Element\n.*?END Element\n", src[style], re.S) if re.search(rf"^\s*Name\s+{re.escape(ename)}\s*$", m, re.M))
        if ename == "Time":                                 # Time in EpSec instead of the scenario's UTCG
            b, n = re.subn(r"UseScenUnits\s+Yes\n", EPSEC_UNITS, b)
            assert n == 1, "Time element has no UseScenUnits line to override"
        blocks.append(b)
    s = src["LLA Position"]
    head, tail = s.split("BEGIN Element\n", 1)[0], s.rsplit("END Element\n", 1)[1]
    out = head + "".join(blocks) + tail
    out = re.sub(r"NumElements\s+\d+", f"NumElements\t\t{len(blocks)}", out)
    out = re.sub(r"(BEGIN ReportStyle\nName\s+).+", rf"\g<1>{FS_NAME}", out)
    out = re.sub(r"(\n\s*Title\s+)LLA Position[^\n]*", rf"\g<1>{FS_NAME}", out, count=1)      # whole title line, not just the prefix
    assert out.count("BEGIN Element") == len(FS_FIELDS) and FS_NAME in out
    p = FOLDER / f"{FS_NAME}.rst"
    p.write_text(out, encoding="utf-8")
    return p


def export_flight_summary(root, step_s=60):
    track("T4 FlightSummary.csv", "In progress")
    connect(root, f'ReportStyle * Load "{make_flight_style()}"')
    csv_path = FOLDER / "FlightSummary.csv"
    connect(root, f'ReportCreate */Aircraft/{AC} Style "{FS_NAME}" Type Export File "{csv_path}" TimeStep {step_s}')
    return csv_path


ORIG_STEP_S = 10          # scenario's saved animation step (UpdateDelta in the .sc); restored after any recording


def _fmt(d):
    return d.strftime("%d %b %Y %H:%M:%S.") + f"{d.microsecond // 1000:03d}"


def record_ica_flyover(root, sc, half_window_s=120, step_s=1, fps=20, kbps=3000, cam_alt_km=60, timeout_s=900):
    """T6: WMV of CertAircraft flying over Ica. Camera: Earth-fixed, straight above Ica; window = +-half_window_s around the aircraft's
    Ica waypoint (waypoint 3); frames = 2*half_window_s/step_s, so duration = frames/fps. Animation settings are always restored."""
    import time
    track("T6 AircraftView.wmv", "In progress")
    ac = sc.Children.Item(AC)
    t_ica = _t(ac.Route.Waypoints.Item(2).Time)                                    # waypoint 3 = Ica
    t0, t1 = t_ica - dt.timedelta(seconds=half_window_s), t_ica + dt.timedelta(seconds=half_window_s)
    lat, lon, _ = sc.Children.Item("Ica").Position.QueryPlanetodetic()
    end_s = (t1 - _t(sc.StartTime)).total_seconds()
    before = connect(root, "GetAnimationData * TimePeriod"), connect(root, "GetAnimationData * Mode")
    out = FOLDER / "AircraftView.wmv"
    assert not out.exists(), "move the previous AircraftView.wmv to a backup first"
    try:
        connect(root, "VO * View Home")
        connect(root, 'VO * View SetReferenceFrame "CentralBody/Earth Fixed Axes"')
        lat_c = math.degrees(math.atan((1 - 0.00669437999014) * math.tan(math.radians(lat))))        # ViewerPosition declination is GEOCENTRIC
        connect(root, f"VO * ViewerPosition {lat_c:.4f} {lon} {int(6378137 + cam_alt_km * 1000)}")  # range from Earth centre, metres
        connect(root, f'SetAnimation * StartAndCurrentTime "{_fmt(t0)}" EndTime "{_fmt(t1)}" TimeStep {step_s}')
        connect(root, f'RecordMovie3D * FileFormat WMV OutputDir "{FOLDER}" Prefix AircraftView FrameRate {fps} BitRate {kbps}')
        connect(root, "RecordMovie3D * Record On")
        connect(root, "Animate * Start Forward End")
        t_start = time.time()
        while root.CurrentTime < end_s - 1e-6 and time.time() - t_start < timeout_s:
            time.sleep(1)
        print(f"animation reached t={root.CurrentTime:.1f} s of {end_s:.1f} s after {time.time() - t_start:.0f} s")
    finally:
        connect(root, "RecordMovie3D * Record Off")
        connect(root, "Animate * Reset")
        connect(root, f"SetAnimation * StartAndCurrentTime UseAnalysisStartTime EndTime UseAnalysisStopTime TimeStep {ORIG_STEP_S}")
        connect(root, "SetAnimation * EndMode Continuous")                          # original mode was plain "Using Time Step"
        connect(root, f'VO * UseStoredView "{QUAKE_VIEW}"')
        after = connect(root, "GetAnimationData * TimePeriod"), connect(root, "GetAnimationData * Mode")
        print("animation before:", before, "\nanimation after :", after)
    return out, before, after, (_fmt(t0), _fmt(t1))


def _t(s):
    return dt.datetime.strptime(s.split(".")[0], "%d %b %Y %H:%M:%S") + dt.timedelta(milliseconds=int(s.split(".")[1][:3]))


def access_to_runway(sc):
    """Compute Aircraft->Runway access (uses both objects' constraints: Runway min elevation 2 deg + line of sight)."""
    acc = sc.Children.Item(AC).GetAccessToObject(sc.Children.Item("Runway"))
    acc.ComputeAccess()
    iv = acc.ComputedAccessIntervalTimes
    out = []
    for i in range(iv.Count):
        a, b = iv.GetInterval(i)[:2]
        out.append((a, b))
    return out


def flight_interval(ac):
    i = ac.Vgt.EventIntervals.Item("EphemerisTimeSpan").FindInterval().Interval
    return i.Start, i.Stop


def summarize(ac, ivs):
    f0, f1 = flight_interval(ac)
    flight = (_t(f1) - _t(f0)).total_seconds()
    have = sum((_t(b) - _t(a)).total_seconds() for a, b in ivs)
    return f"{len(ivs)} interval(s), access {have:.0f} s of {flight:.0f} s flight ({100*have/flight:.1f}%)", have >= flight - 1


def sweep(sc, ac, alts):
    res = []
    for h in alts:
        set_waypoints(sc, ac, altitude_km=h)
        ivs = access_to_runway(sc)
        msg, full = summarize(ac, ivs)
        print(f"alt {h:7.3f} km -> {msg}{'  <-- FULL' if full else ''}")
        res.append((h, full))
    return res


def readback(sc):
    ac = sc.Children.Item(AC)
    r = ac.Route
    print("RouteType  :", ac.RouteType, "(9 = Great Arc) |", type(r).__name__)
    for i in range(r.Waypoints.Count):
        w = r.Waypoints.Item(i)
        print(f"  wp{i+1}: lat {w.Latitude:.5f} lon {w.Longitude:.5f} alt {w.Altitude} km speed {w.Speed:.5f} km/s turn {w.TurnRadius} km time {w.Time}")
    iv = ac.Vgt.EventIntervals.Item("EphemerisTimeSpan").FindInterval().Interval   # route.EphemerisInterval reports start==stop (API quirk)
    print("Ephemeris  :", iv.Start, "->", iv.Stop)
    a = ac.Graphics.Attributes
    print("Route color:", a.Color.GetRGB(), "| line width enum value:", int(a.Line.Width))
    print("Model file :", ac.VO.Model.ModelData.Filename, "| type", ac.VO.Model.ModelType)
    print("Attitude   : profile", ac.Attitude.Basic.ProfileType, "(24 = Coordinated Turn)")
    if ac.Children.Contains(T.eSensor, CAM):
        p = ac.Children.Item(CAM).Pattern
        print(f"{CAM}: {type(p).__name__} half angles H {p.HorizontalHalfAngle} V {p.VerticalHalfAngle} -> FOV {2*p.HorizontalHalfAngle} x {2*p.VerticalHalfAngle} deg")


if __name__ == "__main__":
    app, root, sc = attach()
    steps = sys.argv[1:] or ["aircraft"]
    if "aircraft" in steps:
        ac = create_aircraft(sc)
        print("waypoints:", set_waypoints(sc, ac))
        print("line width before:", style_aircraft(ac))
        create_camera(ac)
        root.SaveScenario()
    if "sweep" in steps:
        sweep(sc, sc.Children.Item(AC), [10.668, 11, 11.5, 12, 12.5, 13, 13.5, 14, 15])
    if "t6" in steps:
        out, before, after, win = record_ica_flyover(root, sc)
        print("wmv:", out, "window:", win, "exists:", out.exists(), "bytes:", out.stat().st_size if out.exists() else None, "| restored:", before == after)
        root.SaveScenario()
    if "t4" in steps:
        p = export_flight_summary(root)
        print("exported:", p, "|", p.stat().st_size, "bytes")
        print(p.read_text(errors="replace")[:900])
    if "fine" in steps:
        sweep(sc, sc.Children.Item(AC), [13.6, 13.7, 13.8, 13.9])
    if "final" in steps:                                   # smallest round altitude with ONE unbroken access interval
        ac = sc.Children.Item(AC)
        set_waypoints(sc, ac, altitude_km=FINAL_ALT_KM)
        ivs = access_to_runway(sc)
        msg, full = summarize(ac, ivs)
        print(f"FINAL alt {FINAL_ALT_KM} km -> {msg}; intervals {ivs}")
        assert full and len(ivs) == 1, "final altitude does not give full runway access"
        track("T7 altitude + runway access", "Needs verification", f"{FINAL_ALT_KM} km: {msg}")
        root.SaveScenario()
    readback(sc)
