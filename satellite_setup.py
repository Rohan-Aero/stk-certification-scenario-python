"""Part 3: CertSatellite (via Connect), cubesat model, Sat_Camera, first access to Ica, SatView.bmp, SatCamera_to_Ica report, T10 comparison.
Usage: satellite_setup.py <step>...   steps: sat | access | snap | report | compare"""
import re
import sys

from agi.stk13 import stkobjects as so
from agi.stk13.stkobjects import AgESTKObjectType as T

from aircraft_setup import attach, AC, CAM, FOLDER, QUAKE_VIEW, _t, _fmt
from stk_common import connect, track, log, HERE

SAT, SAT_CAM, TARGET = "CertSatellite", "Sat_Camera", "Ica"
SAT_INC = 15.0                                              # the one orbital element the exercise specifies
SAT_MODEL = r"STKData\VO\Models\Space\cubesat_3u.glb"
SAT_FOV_FULL_DEG = 60.0                                     # Simple Conic is defined by the HALF angle (STK help: "specified cone half angle")


def satellite_commands():
    """The exact Connect commands that created/set the satellite, taken from STK-run log (not retyped)."""
    lines = [m.group(1) for ln in open(HERE / "stk_run.log", encoding="utf-8", errors="replace")
             if (m := re.search(r"CONNECT> ((?:New / \*/Satellite CertSatellite|SetState \*/Satellite/CertSatellite).*)$", ln.rstrip("\n")))]
    out = []
    for c in lines:                                         # keep the last occurrence of each distinct command, in first-seen order
        if c in out:
            out.remove(c)
        out.append(c)
    return out


def create_satellite(root, sc):
    track("Satellite", "In progress")
    if not sc.Children.Contains(T.eSatellite, SAT):
        connect(root, f"New / */Satellite {SAT}")
    sat = sc.Children.Item(SAT)
    p = sat.Propagator
    cl = p.InitialState.Representation.ConvertTo(so.AgEOrbitStateType.eOrbitStateClassical)
    a_m, e = round(cl.SizeShape.SemiMajorAxis * 1000, 3), cl.SizeShape.Eccentricity
    w, raan, ta = cl.Orientation.ArgOfPerigee, cl.Orientation.AscNode.Value, cl.Location.Value
    assert e == 0.0 and cl.CoordinateSystemType == so.AgECoordinateSystem.eCoordinateSystemICRF, "unexpected default orbit; inspect before assuming"
    assert cl.SizeShapeType == 4 and cl.LocationType == 5, "default elements are not SMA/true-anomaly"       # e = 0 so mean anomaly == true anomaly
    epoch = p.InitialState.OrbitEpoch.TimeInstant
    cmd = f'SetState */Satellite/{SAT} Classical TwoBody UseScenarioInterval 60 ICRF "{epoch}" {a_m} {e} {SAT_INC} {w} {raan} {ta}'
    connect(root, cmd)
    return sat


def set_model_and_camera(sat):
    track("Sat model + camera", "In progress")
    sat.VO.Model.ModelType = so.AgEModelType.eModelFile
    sat.VO.Model.ModelData.Filename = SAT_MODEL
    if not sat.Children.Contains(T.eSensor, SAT_CAM):
        sat.Children.New(T.eSensor, SAT_CAM)
    sn = sat.Children.Item(SAT_CAM)
    sn.SetPatternType(so.AgESnPattern.eSnSimpleConic)
    sn.Pattern.ConeAngle = SAT_FOV_FULL_DEG / 2
    return sn


def write_long_description(sc):
    cmds = satellite_commands()
    assert len(cmds) >= 2 and cmds[0].startswith("New /") and cmds[-1].startswith("SetState"), f"unexpected command log: {cmds}"
    sc.LongDescription = ("CertSatellite was created with STK Connect. Commands as executed:\n" + "\n".join(f"  {c}" for c in cmds)
                          + "\nOnly inclination was set (15 deg). All other elements are the defaults STK gave the new satellite "
                            "(TwoBody, ICRF, a=6678.137 km, e=0, argp=0, RAAN=0, true anomaly=0, epoch = scenario start).")
    return cmds


def readback(sc):
    sat = sc.Children.Item(SAT)
    cl = sat.Propagator.InitialState.Representation.ConvertTo(so.AgEOrbitStateType.eOrbitStateClassical)
    iv = sat.Vgt.EventIntervals.Item("EphemerisTimeSpan").FindInterval().Interval
    print(f"propagator type {sat.PropagatorType} ({type(sat.Propagator).__name__}) | epoch {sat.Propagator.InitialState.OrbitEpoch.TimeInstant} | ephemeris {iv.Start} -> {iv.Stop}")
    print(f"a={cl.SizeShape.SemiMajorAxis} km e={cl.SizeShape.Eccentricity} i={cl.Orientation.Inclination} argp={cl.Orientation.ArgOfPerigee} raan={cl.Orientation.AscNode.Value} ta={cl.Location.Value}")
    print("model:", sat.VO.Model.ModelData.Filename)
    sn = sat.Children.Item(SAT_CAM)
    print(f"{SAT_CAM}: {type(sn.Pattern).__name__} ConeAngle (half) = {sn.Pattern.ConeAngle} -> full FOV {2 * sn.Pattern.ConeAngle} deg")
    print("Scenario LongDescription:\n" + sc.LongDescription)


def access_intervals(sc, from_obj, to_name=TARGET):
    acc = from_obj.GetAccessToObject(sc.Children.Item(to_name))
    acc.ComputeAccess()
    iv = acc.ComputedAccessIntervalTimes
    return [iv.GetInterval(i)[:2] for i in range(iv.Count)]


def cameras(sc):
    return sc.Children.Item(SAT).Children.Item(SAT_CAM), sc.Children.Item(AC).Children.Item(CAM)


def set_time_to_first_access(root, sc):
    """T8 prep: first Sat_Camera->Ica access start, then set the animation clock to it (start/stop of the animation period untouched)."""
    sat_cam, _ = cameras(sc)
    ivs = access_intervals(sc, sat_cam)
    assert ivs, "Sat_Camera has no access to Ica: do NOT invent orbital elements, report it"
    first = ivs[0][0]
    connect(root, f'SetAnimation * CurrentTime "{first}"')
    return first, ivs


def snap_satview(root):
    """T8: 3D view of CertSatellite itself (camera at Ica looking at the satellite, so the model, label and Sat_Camera cone are visible)
    at the current (first-access) time, saved with VO SnapFrame as SatView.bmp. (A view FROM the sensor cannot show the satellite.)"""
    track("T8 SatView.bmp", "In progress")
    out = FOLDER / "SatView.bmp"
    assert not out.exists(), "move the previous SatView.bmp to a backup first"
    connect(root, f"VO * ViewFromTo Normal From Place/{TARGET} To Satellite/{SAT}")
    connect(root, "VO * ViewFromTo Reset")
    connect(root, f'VO * SnapFrame ToFile "{FOLDER / "SatView"}"')                  # STK appends .bmp (default snapshot format)
    return out


def add_aer_quick_report(root):
    """T9: Access AER quick report from Sat_Camera to Ica (azimuth, elevation, range)."""
    track("T9 SatCamera_to_Ica", "In progress")
    if "SatCamera_to_Ica" not in " ".join(connect(root, "QuickReport_RM * GetList")):
        connect(root, f'QuickReportAdd * Name "SatCamera_to_Ica" Type Report Style "AER" FromObject Satellite/{SAT}/Sensor/{SAT_CAM} Object Place/{TARGET}')
    return "\n".join(connect(root, 'QuickReport_RM * GetReport "SatCamera_to_Ica"'))


def compare_t10(sc):
    """T10: which camera accesses Ica first, and which has the longest access (single longest interval; totals shown too)."""
    sat_cam, ac_cam = cameras(sc)
    res = {}
    for name, o in (("Aircraft camera (AC_Camera)", ac_cam), ("Satellite camera (Sat_Camera)", sat_cam)):
        ivs = access_intervals(sc, o)
        durs = [(_t(b) - _t(a)).total_seconds() for a, b in ivs]
        res[name] = {"intervals": ivs, "durations": durs, "first_start": ivs[0][0] if ivs else None,
                     "longest": max(durs) if durs else 0.0, "total": sum(durs)}
    first = min((v["first_start"] for v in res.values() if v["first_start"]), key=_t)
    first_who = [k for k, v in res.items() if v["first_start"] == first][0]
    longest_who = max(res, key=lambda k: res[k]["longest"])
    total_who = max(res, key=lambda k: res[k]["total"])
    return res, first_who, longest_who, total_who


def t10_text(res, first_who, longest_who, total_who):
    lines = ["T10 - access to Ica: aircraft camera vs satellite camera (computed by STK, scenario STK_Cert_RohanPatel_V13)", ""]
    for k, v in res.items():
        lines.append(f"{k}:")
        for (a, b), d in zip(v["intervals"], v["durations"]):
            lines.append(f"   {a}  ->  {b}   ({d:.3f} s)")
        lines.append(f"   first access starts {v['first_start']} | longest single interval {v['longest']:.3f} s | total {v['total']:.3f} s")
    lines += ["", f"Accesses Ica FIRST: {first_who}", f"LONGEST single access: {longest_who}", f"Longest total access time: {total_who}",
              "Note: the aircraft camera's access is split in two because the aircraft's banked U-turn at Ica briefly tilts the nadir-pointing camera away from Ica."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    app, root, sc = attach()
    steps = sys.argv[1:] or ["sat"]
    if "sat" in steps:
        sat = create_satellite(root, sc)
        set_model_and_camera(sat)
        write_long_description(sc)
        root.SaveScenario()
        readback(sc)
    if "t8" in steps:
        first, ivs = set_time_to_first_access(root, sc)
        print("first Sat_Camera->Ica access:", first, "| intervals:", ivs)
        out = snap_satview(root)
        connect(root, f'VO * UseStoredView "{QUAKE_VIEW}"')                           # recalling a stored view also restores its saved TIME (18:54:00)...
        connect(root, f'SetAnimation * CurrentTime "{first}"')                        # ...so set the first-access time again afterwards
        print("SatView:", out, out.exists(), out.stat().st_size if out.exists() else None, "| clock now", root.CurrentTime, "s from epoch")
        root.SaveScenario()
    if "t9" in steps:
        print(add_aer_quick_report(root))
        root.SaveScenario()
    if "t10" in steps:
        res, f, l, tt = compare_t10(sc)
        txt = t10_text(res, f, l, tt)
        (FOLDER / "T10_AccessComparison.txt").write_text(txt, encoding="utf-8")
        print(txt)
