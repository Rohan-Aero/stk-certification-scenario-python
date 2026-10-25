"""Phase 2: scenario + 5 h window + Terrain Server off, saved in its own folder, then read back."""
import datetime as dt
import sys

from stk_common import HERE, get_app, connect, track, log

NAME = "STK_Cert_RohanPatel_V13"          # "V13" per exercise naming; installed build below
STK_BUILD = "13.1.0.739"
START, STOP = "28 Oct 2011 18:54:00.000", "28 Oct 2011 23:54:00.000"
FOLDER = HERE / NAME
SC_FILE = FOLDER / f"{NAME}.sc"


def parse(s):  # STK returns e.g. "28 Oct 2011 18:54:00.000"
    return dt.datetime.strptime(s.split(".")[0], "%d %b %Y %H:%M:%S")


def create():
    app = get_app()                              # keep `app` referenced: if it is GC'd, root's COM pointer dies
    root = app.Root
    assert root.UnitPreferences.GetCurrentUnitAbbrv("DateFormat") == "UTCG", "DateFormat is not UTCG"
    log.info("attached pid %s, STK %s", app.ProcessID, STK_BUILD)
    track("Scenario", "In progress", f"pid {app.ProcessID}, STK {STK_BUILD}")
    track("Terrain", "In progress")

    sc = root.CurrentScenario
    if sc is None:
        root.NewScenario(NAME)
        sc = root.CurrentScenario
    else:                                        # reuse only our own scenario, never someone else's
        assert sc.InstanceName == NAME, f"scenario {sc.InstanceName!r} is open; refusing to touch it"
    sc.SetTimePeriod(START, STOP)
    try:                                         # Basic > Terrain > "Use terrain server for analysis"
        sc.UseTerrainServerForAnalysis = False
    except RuntimeError as e:                    # seen on 13.1.0.739: setter refused; readback decides
        log.warning("UseTerrainServerForAnalysis setter refused: %s", e)
        print("NOTE: terrain setter refused:", e)

    if not SC_FILE.exists():
        FOLDER.mkdir(exist_ok=True)
        root.SaveScenarioAs(str(SC_FILE))
    return app, root


RUNWAY = [(-12.1501, -76.9957), (-12.1711, -77.0026), (-12.1713, -77.0022), (-12.1503, -76.9953)]
RUNWAY_MIN_ELEV = 2.0   # degrees


def create_runway(root):
    from agi.stk13.stkobjects import AgESTKObjectType as T, AgEAreaType, AgEAccessConstraints as C
    for dim in ("Latitude", "Longitude", "Angle"):     # exercise numbers are degrees; refuse to guess otherwise
        assert root.UnitPreferences.GetCurrentUnitAbbrv(dim) == "deg", f"{dim} unit is not deg"
    sc = root.CurrentScenario
    assert sc.InstanceName == NAME, "wrong scenario open"
    track("Runway", "In progress")

    if not sc.Children.Contains(T.eAreaTarget, "Runway"):
        sc.Children.New(T.eAreaTarget, "Runway")
    at = sc.Children.Item("Runway")
    at.AreaType = AgEAreaType.ePattern
    pts = at.AreaTypeData
    print("points before:", pts.Count)
    pts.RemoveAll()                                    # our own object; start from a known-empty list
    for lat, lon in RUNWAY:                            # order matters: vertex 1..4 as in the exercise
        pts.Add(lat, lon)

    cons = at.AccessConstraints
    assert cons.IsConstraintSupported(C.eCstrElevationAngle), "elevation angle constraint not supported on AreaTarget"
    el = cons.AddConstraint(C.eCstrElevationAngle) if not cons.IsConstraintActive(C.eCstrElevationAngle) \
        else cons.GetActiveConstraint(C.eCstrElevationAngle)
    el.Angle = RUNWAY_MIN_ELEV                         # on an AreaTarget this is a single minimum-angle value (AgAccessCnstrAngle)
    root.SaveScenario()
    return at


def readback_runway(root):
    from agi.stk13.stkobjects import AgEAccessConstraints as C
    at = root.CurrentScenario.Children.Item("Runway")
    pts = [(at.AreaTypeData.Item(i).Lat, at.AreaTypeData.Item(i).Lon) for i in range(at.AreaTypeData.Count)]
    el = at.AccessConstraints.GetActiveConstraint(C.eCstrElevationAngle)
    print("Runway AreaType :", at.AreaType)
    for i, p in enumerate(pts, 1):
        print(f"  vertex {i}: lat {p[0]:.4f}  lon {p[1]:.4f}")
    print("Elevation constraint:", el.ConstraintName, "| enabled:", el.Enabled, "| Angle:", el.Angle, "deg")
    return pts, el


PLACES = {"Ica": (-14.0639, -75.7303), "Paracas": (-13.849, -76.255)}


def create_places(root):
    from agi.stk13.stkobjects import AgESTKObjectType as T
    for dim in ("Latitude", "Longitude"):
        assert root.UnitPreferences.GetCurrentUnitAbbrv(dim) == "deg", f"{dim} unit is not deg"
    sc = root.CurrentScenario
    assert sc.InstanceName == NAME, "wrong scenario open"
    track("Places", "In progress")
    for name, (lat, lon) in PLACES.items():
        if not sc.Children.Contains(T.ePlace, name):
            sc.Children.New(T.ePlace, name)
        sc.Children.Item(name).Position.AssignGeodetic(lat, lon, 0.0)   # altitude 0 km
    root.SaveScenario()


def readback_places(root):
    out = {}
    for name in PLACES:
        lat, lon, alt = root.CurrentScenario.Children.Item(name).Position.QueryPlanetodetic()
        out[name] = (lat, lon)
        print(f"{name:8s} lat {lat:.4f}  lon {lon:.4f}  alt {alt:.4f} km")
    return out


TL_VIEW = "Scenario Availability"                      # the Timeline content view STK creates by default
TL_COMP = "Place/Ica LightingIntervals Collection of Interval Lists"


def add_ica_lighting_timeline(root):
    track("T2 Ica lighting timeline", "In progress")
    try:                                               # make re-runs safe: drop an existing row first
        connect(root, f'Timeline * TimeComponent Remove ContentView "{TL_VIEW}" "{TL_COMP}"')
    except RuntimeError:
        pass
    connect(root, f'Timeline * TimeComponent Add ContentView "{TL_VIEW}" "{TL_COMP}"')
    connect(root, "Timeline * Refresh")
    root.SaveScenario()


QUAKE_VIEW = "Quake Region"
# declination/right-ascension (= lat/lon in Earth Fixed) of the Runway/Ica/Paracas bounding-box centre; range (m)
# from Earth centre = 6378 km + ~650 km, which frames all three with margin in the 3D window (checked by snapshot)
QUAKE_CAM = (-13.107, -76.366, 7030000)


def set_quake_region_view(root):
    track("T1 Quake Region view", "In progress")
    connect(root, "Animate * Reset")                   # animation clock was left at "today"; go to scenario start
    connect(root, 'VO * View SetReferenceFrame "CentralBody/Earth Fixed Axes"')   # keep Peru framed as Earth rotates
    connect(root, "VO * ViewerPosition %s %s %s" % QUAKE_CAM)
    connect(root, f'VO * SaveStoredView "{QUAKE_VIEW}"')
    root.SaveScenario()


QR_NAME = "Ica_LatLon"
STYLE_SRC = r"C:\Program Files\AGI\STK_ODTK 13\STKData\Styles\Place\LLA Position.rst"   # STK's own Place style (Lat, Lon, Alt)


def make_latlon_style():
    """Derive a Lat+Lon-only report style from STK's shipped Place 'LLA Position' style; keep a copy in the scenario folder."""
    import re
    s = open(STYLE_SRC, encoding="utf-8").read()
    s = re.sub(r"\n?BEGIN Element\s+Name\s+LLA State-Alt.*?END Element\n", "\n", s, flags=re.S)   # drop the Alt column
    s = s.replace("NumElements\t\t3", "NumElements\t\t2")
    s = s.replace("Name\t\tLLA Position", f"Name\t\t{QR_NAME}").replace("Title\t\tLLA Position", f"Title\t\t{QR_NAME}")
    assert "LLA State-Alt" not in s and "NumElements\t\t2" in s and f"Name\t\t{QR_NAME}" in s, "style edit did not apply"
    p = FOLDER / f"{QR_NAME}.rst"
    p.write_text(s, encoding="utf-8")
    return p


def create_ica_latlon_quick_report(root):
    track("T3 Ica_LatLon report", "In progress")
    style = make_latlon_style()
    connect(root, f'ReportStyle * Load "{style}"')     # documented: copies the .rst into STK's user Styles folder
    if QR_NAME not in " ".join(connect(root, "QuickReport_RM * GetList")):
        connect(root, f'QuickReportAdd * Name "{QR_NAME}" Type Report Style "{QR_NAME}" Object Place/Ica')
    root.SaveScenario()


def readback(root):
    sc = root.CurrentScenario
    print("Scenario name :", sc.InstanceName)
    print("Start         :", sc.StartTime)
    print("Stop          :", sc.StopTime)
    print("Duration      :", parse(sc.StopTime) - parse(sc.StartTime))
    print("Epoch         :", sc.Epoch)
    print("Terrain server for analysis   :", sc.UseTerrainServerForAnalysis)
    print("  ...for AzEl mask (not changed):", sc.UseTerrainServerForAzElMask)
    print("  ...for LOS mask  (not changed):", sc.UseTerrainServerForLOSTerrainMask)
    print("Connect TerrainServer_RM Server  :", connect(root, "TerrainServer_RM / Server"))
    print("Saved file    :", SC_FILE, "| exists:", SC_FILE.exists(), "| bytes:", SC_FILE.stat().st_size)
    return sc


if __name__ == "__main__" and "runway" in sys.argv:
    app, r = create()                                  # idempotent: reuses our open scenario
    create_runway(r)
    pts, el = readback_runway(r)
    ok = (len(pts) == 4 and all(abs(a - b) < 1e-9 for p, q in zip(pts, RUNWAY) for a, b in zip(p, q))
          and el.Enabled and abs(el.Angle - RUNWAY_MIN_ELEV) < 1e-9)
    track("Runway", "Needs verification" if ok else "Blocked", "API readback " + ("ok" if ok else "MISMATCH"))
    print("runway API readback ok:", ok)
elif __name__ == "__main__" and "t3" in sys.argv:
    app, r = create()
    create_ica_latlon_quick_report(r)
    print("quick reports:", connect(r, "QuickReport_RM * GetList"))
    print("--- report text ---")
    for line in connect(r, f'QuickReport_RM * GetReport "{QR_NAME}"'):
        print(line)
    track("T3 Ica_LatLon report", "Needs verification", "style loaded; QuickReportAdd fails in this build, see notes")
elif __name__ == "__main__" and "t1" in sys.argv:
    app, r = create()
    set_quake_region_view(r)
    names = connect(r, "VO_R * StoredViewNames")
    ok = f'"{QUAKE_VIEW}"' in " ".join(names)          # STK returns one space-separated string, not a list
    track("T1 Quake Region view", "Needs verification" if ok else "Blocked", f"stored views: {names}")
    print("stored views:", names)
elif __name__ == "__main__" and "t2" in sys.argv:
    app, r = create()
    add_ica_lighting_timeline(r)
    track("T2 Ica lighting timeline", "Needs verification", "command accepted; check saved TimelinePrefs.xml")
    print("T2 command accepted; verify with deliverable_validation.py")
elif __name__ == "__main__" and "places" in sys.argv:
    app, r = create()
    create_places(r)
    got = readback_places(r)
    ok = all(abs(got[n][0] - PLACES[n][0]) < 1e-9 and abs(got[n][1] - PLACES[n][1]) < 1e-9 for n in PLACES)
    track("Places", "Needs verification" if ok else "Blocked", "API readback " + ("ok" if ok else "MISMATCH"))
    print("places API readback ok:", ok)
elif __name__ == "__main__":
    app, r = create()
    sc = readback(r)
    ok_time = (sc.InstanceName == NAME and sc.StartTime.startswith(START[:-4])
               and sc.StopTime.startswith(STOP[:-4])
               and parse(sc.StopTime) - parse(sc.StartTime) == dt.timedelta(hours=5))
    ok_terr = sc.UseTerrainServerForAnalysis is False
    track("Scenario", "Needs verification" if ok_time else "Blocked", "API readback " + ("ok" if ok_time else "MISMATCH"))
    track("Terrain", "Needs verification" if ok_terr else "Blocked", "API readback " + ("ok" if ok_terr else "MISMATCH"))
    track("Saved", "Needs verification", str(SC_FILE))
    print("time ok:", ok_time, "| terrain ok:", ok_terr)
