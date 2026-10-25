"""Part 1 verification. File checks read the SAVED scenario files (not the live API); live checks ask the running STK."""
import datetime as dt
import math
import re

from scenario_setup import NAME, SC_FILE, START, STOP, RUNWAY, RUNWAY_MIN_ELEV, PLACES, QUAKE_VIEW, QR_NAME, TL_VIEW
from stk_common import track, _stk_pids, get_app, connect

D = SC_FILE.parent
read = lambda name: (D / name).read_text(errors="replace")


def check_scenario():
    t = read(SC_FILE.name)
    name = re.search(r"BEGIN Scenario\s+Name\s+(\S+)", t)
    iv = re.search(r"BEGIN Interval\s+Start\s+(.+?)\s*\n\s*Stop\s+(.+?)\s*\n", t)
    got = (name and name.group(1), iv and iv.group(1), iv and iv.group(2))
    want = (NAME, START + "000000", STOP + "000000")     # file stores 9 fractional digits
    return got == want, f"got {got}"


def check_terrain_off():
    m = re.search(r"BEGIN StreamingTerrain\s+UseCurrentStreamingTerrainServer\s+(\w+)", read(SC_FILE.name))
    return bool(m) and m.group(1) == "No", f"UseCurrentStreamingTerrainServer={m and m.group(1)}"


def check_runway():
    t = read("Runway.at")
    blk = re.search(r"BEGIN PolygonPoints(.*?)END PolygonPoints", t, re.S).group(1)
    pts = [tuple(map(float, ln.split()[:2])) for ln in blk.strip().splitlines()]
    el = re.search(r"^\s*ElevationAngle\s+(\S+)", t, re.M)
    shape_ok = len(pts) == 5 and pts[4] == pts[0] and all(abs(a - b) < 1e-9 for p, q in zip(pts, RUNWAY) for a, b in zip(p, q))
    el_ok = bool(el) and abs(float(el.group(1)) - RUNWAY_MIN_ELEV) < 1e-9
    return shape_ok and el_ok, f"{len(pts)} pts (STK repeats pt 1 to close), first4_match={shape_ok}, ElevationAngle={el and el.group(1)}"


def check_places():
    res = []
    for name, (lat, lon) in PLACES.items():
        t = read(f"{name}.plc")
        g = lambda k: float(re.search(rf"^\s*{k}\s+(\S+)", t, re.M).group(1))
        res.append((name, abs(g("EcfLatitude") - lat) < 1e-9 and abs(g("EcfLongitude") - lon) < 1e-9, g("EcfLatitude"), g("EcfLongitude")))
    return all(r[1] for r in res), res


def check_t1_file():
    t = read(SC_FILE.name.replace(".sc", ".sc3"))
    m = re.search(rf"BEGIN View\s+ViewName\s+{QUAKE_VIEW}\b(.{{0,600}})", t, re.S)
    return bool(m) and re.search(r"Name\s+Fixed", m.group(1)) is not None, "stored view in .sc3, frame = Earth Fixed" if m else "not found"


def check_t2_file():     # regex, not an XML parser: STK writes this file in a fixed simple format
    t = read(f"{NAME}TimelinePrefs.xml")
    for m in re.finditer(r'<Row ClassName = "Place" ComponentName = "LightingIntervals"[^>]*?Path = "([^"]*)"[^>]*>(.*?)</Row>', t, re.S):
        if m.group(1).endswith("/Place/Ica"):
            iv = {n: (a, b) for n, a, b in re.findall(r'Name = "(\w+)"[^>]*?StartTime = "([^"]+)" StopTime = "([^"]+)"', m.group(2))}
            return {"Sunlight", "Penumbra", "Umbra"} <= set(iv), f"Ica LightingIntervals row in view '{TL_VIEW}': {iv}"
    return False, "no Ica LightingIntervals row"


def check_t3_file():
    t = read(SC_FILE.name)
    m = re.search(rf"BEGIN Report\s+Name\s+{QR_NAME}\s+Type\s+Report\s+BaseDir\s+\w+\s+Style\s+{QR_NAME}.*?Instance\s+(\S+)", t, re.S)
    rst = read(f"{QR_NAME}.rst")
    cols = re.findall(r"Element\s+(Lat|Lon|Alt)\b", rst)
    return bool(m) and m.group(1) == "Place/Ica" and cols == ["Lat", "Lon"], f"QuickReports entry instance={m and m.group(1)}, style columns={cols}"


# ---------------- Part 2 ----------------
from aircraft_setup import AC, CAM, FINAL_ALT_KM, FS_NAME, TURN_RADIUS_KM, FOV_FULL_DEG, access_to_runway, summarize, flight_interval


def check_aircraft_file():
    t = read(f"{AC}.ac")
    rl = lambda k: float(re.search(rf"^\s*{k}\s+(\S+)", read("Runway.at"), re.M).group(1))
    want = [(rl("EcfLatitude"), rl("EcfLongitude")), PLACES["Paracas"], PLACES["Ica"], (rl("EcfLatitude"), rl("EcfLongitude"))]
    blk = re.search(r"BEGIN Waypoints(.*?)END Waypoints", t, re.S).group(1)
    rows = [list(map(float, ln.split())) for ln in blk.strip().splitlines()]
    pos_ok = len(rows) == 4 and all(abs(r[1] - w[0]) < 1e-9 and abs(r[2] - w[1]) < 1e-9 for r, w in zip(rows, want))
    turn_ok = all(abs(r[6] - TURN_RADIUS_KM * 1000) < 1e-6 for r in rows)          # file stores metres
    alt_ok = all(abs(r[3] - FINAL_ALT_KM * 1000) < 1e-6 for r in rows)
    ga = re.search(r"InterpolationMethod\s+GreatArc", t) is not None
    color = re.search(r"AllColors\s+#ffffff\s+LineStyle\s+0\s+LineWidth\s+3\b", t) is not None   # STK default width in file = 2, so 3 = one level thicker
    att = re.search(r"BEGIN Profile\s+Name\s+AircraftCoordTurn", t) is not None
    ok = all([pos_ok, turn_ok, alt_ok, ga, color, att])
    return ok, f"GreatArc={ga}, waypoint order/coords={pos_ok}, turn 1 km={turn_ok}, alt {FINAL_ALT_KM} km={alt_ok}, white+width3={color}, CoordTurn={att}"


def check_model_camera_file():
    m = re.search(r"^ModelPath\s+(\S+)", read(f"{AC}.ac3"), re.M)
    s = read(f"{CAM}.sn")
    ud = float(re.search(r"UpDownAngle\s+(\S+)", s).group(1)); ss = float(re.search(r"SideToSideAngle\s+(\S+)", s).group(1))
    ok = bool(m) and m.group(1).replace("/", "\\").endswith("uav.glb") and ud == FOV_FULL_DEG and ss == FOV_FULL_DEG and "BEGIN Rectangular" in s
    return ok, f"ModelPath={m and m.group(1)}, rectangular FOV {ss} x {ud} deg (file stores full angles)"


_A, _F = 6378.137, 1 / 298.257223563        # WGS84 (km)


def _ecef(lat, lon, h):
    la, lo = math.radians(lat), math.radians(lon)
    n = _A / math.sqrt(1 - _F * (2 - _F) * math.sin(la) ** 2)
    return [(n + h) * math.cos(la) * math.cos(lo), (n + h) * math.cos(la) * math.sin(lo), (n * (1 - _F) ** 2 + h) * math.sin(la)]


def _sub(a, b): return [x - y for x, y in zip(a, b)]
def _dot(a, b): return sum(x * y for x, y in zip(a, b))
def _norm(a): return math.sqrt(_dot(a, a))
def _cross(a, b): return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def check_t4_csv():
    """Header + EpSec, then recompute the data from the saved waypoints. No vertex-to-vertex timing model: STK cuts the 1 km-radius
    corners, so rows within 20 s of a waypoint are skipped. The CSV prints lat/lon to 3 decimals (+-55 m), so heading is NOT taken
    from 10.8 km chords; it is compared with the great circle's tangent direction at each point instead."""
    import csv as _csv
    rows = list(_csv.reader(open(D / "FlightSummary.csv", encoding="utf-8")))
    head, data = rows[0], [r for r in rows[1:] if r]
    want_head = ["Time (EpSec)", "Lat (deg)", "Lon (deg)", "Alt (km)", "Azimuth (deg)", "Elevation (deg)", "Velocity (nm/hr)"]
    wp = [list(map(float, ln.split())) for ln in re.search(r"BEGIN Waypoints(.*?)END Waypoints", read(f"{AC}.ac"), re.S).group(1).strip().splitlines()]
    wt, wll, h, v_ms = [w[0] for w in wp], [(w[1], w[2]) for w in wp], wp[0][3] / 1000, wp[0][4]
    num = [[float(x) for x in r] for r in data]                              # raises if any field (incl. Time in EpSec) is not numeric
    t = [r[0] for r in num]
    ep_ok = abs(t[0]) < 1e-6 and all(abs(b - a - 60) < 1e-3 for a, b in zip(t[:-2], t[1:-1])) and abs(t[-1] - wt[-1]) < 0.01
    alt_ok = all(abs(r[3] - FINAL_ALT_KM) < 1e-6 for r in num)
    vel_ok = all(abs(r[6] - v_ms * 3.6 / 1.852) < 0.01 for r in num)         # 350 nm/hr = waypoint speed
    U = [[x / _norm(v) for x in v] for v in (_ecef(*p, h) for p in wll)]
    leg = lambda s: max(k for k in range(len(wt) - 1) if wt[k] <= s + 1e-9) if s < wt[-1] else len(wt) - 2
    far = lambda s: min(abs(s - w) for w in wt) > 20                         # outside any turn
    azi_err = elev_err = xt_max = 0.0
    by_leg, n = {}, 0
    for r in num:
        if not far(r[0]):
            continue
        i, P = leg(r[0]), _ecef(r[1], r[2], r[3])
        nrm = _cross(U[i], U[i + 1]); nrm = [x / _norm(nrm) for x in nrm]
        xt_max = max(xt_max, abs(_dot(nrm, P)))                              # distance from the leg's great-circle plane
        tan = _cross(nrm, P)
        if _dot(tan, _sub(U[i + 1], U[i])) < 0:
            tan = [-x for x in tan]
        la, lo = math.radians(r[1]), math.radians(r[2])
        east, north = [-math.sin(lo), math.cos(lo), 0], [-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)]
        up = [math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)]
        azi_err = max(azi_err, abs((math.degrees(math.atan2(_dot(tan, east), _dot(tan, north))) % 360 - r[4] + 180) % 360 - 180))
        elev_err = max(elev_err, abs(math.degrees(math.asin(_dot(tan, up) / _norm(tan))) - r[5]))
        by_leg.setdefault(i, []).append((r[0], P)); n += 1
    spd_err = 0.0                                                            # speed over a whole leg: rounding errors do not accumulate
    for i, pts in by_leg.items():
        if len(pts) >= 2:
            (t0, p0), (t1, p1) = pts[0], pts[-1]
            spd_err = max(spd_err, abs(_norm(_sub(p1, p0)) / (t1 - t0) * 1000 - v_ms) / v_ms)
    # holistic: constant speed over the filleted path (r = 1 km corners) must reproduce STK's total flight time
    L = sum(math.acos(_dot(U[i], U[i + 1])) * (_A + h) for i in range(3))
    save = 0.0
    for k in (1, 2):
        n1, n2 = _cross(U[k - 1], U[k]), _cross(U[k], U[k + 1])
        ang = math.acos(max(-1, min(1, _dot(n1, n2) / (_norm(n1) * _norm(n2)))))
        save += 2 * TURN_RADIUS_KM * math.tan(ang / 2) - TURN_RADIUS_KM * ang
    t_exp = (L - save) / (v_ms / 1000)
    ok = (head == want_head and ep_ok and alt_ok and vel_ok and n >= 40 and azi_err < 0.1 and elev_err < 0.1
          and spd_err < 0.005 and xt_max < 0.2 and abs(t_exp - wt[-1]) / wt[-1] < 0.005)
    return ok, (f"header={head == want_head}, {len(num)} rows, EpSec 0..{t[-1]} (flight {wt[-1]:.3f})={ep_ok}, alt={alt_ok}, velocity=350nm/hr={vel_ok}; "
                f"{n} straight-flight rows: azimuth vs great-circle tangent {azi_err:.3f} deg, elevation {elev_err:.3f} deg, cross-track {xt_max:.3f} km, "
                f"per-leg speed {100 * spd_err:.3f}%; expected flight time {t_exp:.1f} s vs {wt[-1]:.1f} s")


def check_t5_file():
    m = re.search(r"BEGIN Report\s+Name\s+Aircraft_to_Runway\s+Type\s+Report\s+BaseDir\s+\w+\s+Style\s+Access\b.*?Instance\s+(\S+).*?BEGIN InstanceList\s+Instance\s+(\S+)", read(SC_FILE.name), re.S)
    return bool(m) and (m.group(1), m.group(2)) == (f"Aircraft/{AC}", "AreaTarget/Runway"), f"from/to={m and m.groups()}"


def wmv_seconds(path):
    """Duration from the ASF/WMV header's File Properties Object (play duration minus preroll); no decoder needed."""
    import struct
    b = path.read_bytes()[:65536]
    if b[:16] != bytes.fromhex("3026B2758E66CF11A6D900AA0062CE6C"):
        raise ValueError("not an ASF/WMV file")
    i = b.index(bytes.fromhex("A1DCAB8C47A9CF118EE400C00C205365"))             # File Properties Object GUID
    play100ns, send100ns, preroll_ms = struct.unpack_from("<QQQ", b, i + 64)     # GUID16 + size8 + fileID16 + fileSize8 + created8 + packets8
    return play100ns / 1e7 - preroll_ms / 1000


def check_t6_file():
    p = D / "AircraftView.wmv"
    t = read(SC_FILE.name)
    iv = re.search(r"BEGIN Interval.*?AnimStartUsesAnalStart\s+(\w+)\s+AnimStopUsesAnalStop\s+(\w+)", t, re.S)
    secs = wmv_seconds(p)
    return p.exists() and p.stat().st_size > 50_000 and 10 <= secs <= 15 and iv.groups() == ("Yes", "Yes"), \
        f"{p.name} {p.stat().st_size} bytes, header duration {secs:.2f} s (required 10-15); saved animation start/stop track analysis period={iv and iv.groups()}"


def part2_live(root, sc):
    ac = sc.Children.Item(AC)
    ivs = access_to_runway(sc)
    msg, full = summarize(ac, ivs)
    f0, f1 = flight_interval(ac)
    anim = connect(root, "GetAnimationData * TimePeriod")[0], connect(root, "GetAnimationData * Mode")[0]
    qrs = " ".join(connect(root, "QuickReport_RM * GetList"))
    rpt = "\n".join(connect(root, 'QuickReport_RM * GetReport "Aircraft_to_Runway"')) if "Aircraft_to_Runway" in qrs else ""
    return {f"runway access: {msg}": full and len(ivs) == 1 and ivs[0] == (f0, f1),
            f"animation period restored {anim}": anim == ('"28 Oct 2011 18:54:00.000", "28 Oct 2011 23:54:00.000"', "Using Time Step"),
            "both quick reports listed": "Ica_LatLon" in qrs and "Aircraft_to_Runway" in qrs,
            "quick report shows the flight interval": f1 in rpt and f0 in rpt}


def live_checks():
    if not _stk_pids():
        return None
    app = get_app(); root = app.Root
    views = " ".join(connect(root, "VO_R * StoredViewNames"))
    qrs = " ".join(connect(root, "QuickReport_RM * GetList"))
    rpt = "".join(connect(root, f'QuickReport_RM * GetReport "{QR_NAME}"')) if QR_NAME in qrs else ""
    nums = [float(x) for x in re.findall(r"-?\d+\.\d+", rpt.split("Lon (deg)")[-1])]
    ok_rpt = len(nums) == 2 and abs(nums[0] - PLACES["Ica"][0]) < 5e-4 and abs(nums[1] - PLACES["Ica"][1]) < 5e-4   # report prints 3 decimals
    return {"stored view listed": f'"{QUAKE_VIEW}"' in views, "quick report listed": QR_NAME in qrs,
            f"quick report values {nums}": ok_rpt}


# ---------------- Part 3 ----------------
from satellite_setup import (SAT, SAT_CAM, TARGET, SAT_INC, SAT_FOV_FULL_DEG, SAT_MODEL, satellite_commands, access_intervals, cameras,
                             compare_t10, t10_text)

ORIG_ANIM = {"StartTime": "28 Oct 2011 18:54:00.000000000", "EndTime": "28 Oct 2011 23:54:00.000000000", "UpdateDelta": "10", "RefreshDelta": "0.010000"}


def check_p3_satellite_file():
    t = read(f"{SAT}.sa")
    blk = re.search(r"BEGIN TwoBody(.*?)END TwoBody", t, re.S).group(1)
    g = lambda k: float(re.search(rf"^\s*{k}\s+(\S+)", blk, re.M).group(1))
    elems = dict(a_m=g("RadiusOfPerigee"), e=g("Eccentricity"), inc=g("Inclination"), argp=g("ArgOfPerigee"), raan=g("RightAscension"), ta=g("TrueAnomaly"))
    ok = (abs(elems["inc"] - SAT_INC) < 1e-9 and abs(elems["a_m"] - 6678137.0) < 1e-3 and elems["e"] == 0 and elems["argp"] == 0
          and elems["raan"] == 0 and elems["ta"] == 0 and "OrbElemCoordSys  ICRF" in re.sub(r"\s+", "  ", blk))
    m = re.search(r"^ModelPath\s+(\S+)", read(f"{SAT}.sa3"), re.M)
    model_ok = bool(m) and m.group(1).replace("/", "\\").endswith("cubesat_3u.glb")
    return ok and model_ok, f"TwoBody {elems}, ICRF; model {m and m.group(1)}"


def check_p3_long_description():
    t = read(SC_FILE.name)
    blk = re.search(r"BEGIN LongText(.*?)END LongText", t, re.S)
    cmds = satellite_commands()                                              # parsed from STK-run log of what was really sent
    ok = bool(blk) and len(cmds) >= 2 and all(c in blk.group(1) for c in cmds) and cmds[0].startswith("New / */Satellite CertSatellite") \
        and re.search(r"Classical TwoBody UseScenarioInterval 60 ICRF .* 15\.0 ", cmds[-1]) is not None
    return ok, f"Long Description contains {len(cmds)} logged Connect commands: {cmds}"


def check_p3_sensor_file():
    s = read(f"{SAT_CAM}.sn")
    m = re.search(r"BEGIN Pattern\s+BEGIN SimpleCone\s+ConeAngle\s+(\S+)", s)            # STK's file tag for a Simple Conic pattern
    ok = bool(m) and abs(float(m.group(1)) * 2 - SAT_FOV_FULL_DEG) < 1e-6
    return ok, f"Simple Conic, stored cone half angle {m and m.group(1)} -> full FOV {m and 2 * float(m.group(1)):.6f} deg"


def check_t8_file():
    import struct
    b = (D / "SatView.bmp").read_bytes()
    w, h = struct.unpack_from("<ii", b, 18)
    bpp = struct.unpack_from("<H", b, 28)[0]
    return b[:2] == b"BM" and w > 100 and abs(h) > 100 and len(b) > 100_000, f"valid BMP {w}x{abs(h)} {bpp}bpp {len(b)} bytes (content checked by viewing the frame)"


def check_t9_file():
    m = re.search(r"BEGIN Report\s+Name\s+SatCamera_to_Ica\s+Type\s+Report\s+BaseDir\s+\w+\s+Style\s+AER\b.*?Instance\s+(\S+).*?BEGIN InstanceList\s+Instance\s+(\S+)", read(SC_FILE.name), re.S)
    return bool(m) and m.groups() == (f"Satellite/{SAT}/Sensor/{SAT_CAM}", f"Place/{TARGET}"), f"from/to={m and m.groups()}"


def _edge_range_km(lat_deg, a_km, half_deg):
    """Slant range where a nadir-pointing cone of the given half angle meets the ground at Ica: triangle (Earth centre, satellite, Ica)."""
    p = math.radians(lat_deg); c, s = math.cos(p), math.sin(p)
    B = _A * (1 - _F)
    R = math.sqrt(((_A * _A * c) ** 2 + (B * B * s) ** 2) / ((_A * c) ** 2 + (B * s) ** 2))
    eta = math.radians(half_deg)
    ang_ground = math.pi - math.asin(a_km * math.sin(eta) / R)
    return R * math.sin(math.pi - eta - ang_ground) / math.sin(eta)


def part3_live(root, sc):
    sat_cam, ac_cam = cameras(sc)
    ivs = access_intervals(sc, sat_cam)
    first = ivs[0][0] if ivs else None
    blk = re.search(r"BEGIN Animation(.*?)END Animation", read(SC_FILE.name), re.S).group(1)
    anim = {k: re.search(rf"^\s*{k}\s+(\S.*?)\s*$", blk, re.M).group(1) for k in ("StartTime", "EndTime", "CurrentTime", "UpdateDelta", "RefreshDelta")}
    # AER quick report: parse every (time, az, el, range) row, split per pass
    qrs = " ".join(connect(root, "QuickReport_RM * GetList"))
    rpt = "\n".join(connect(root, 'QuickReport_RM * GetReport "SatCamera_to_Ica"')) if "SatCamera_to_Ica" in qrs else ""
    rows = re.findall(r"^\s+(\d\d \w{3} \d{4} \d\d:\d\d:\d\d\.\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s*$", rpt, re.M)    # data rows only (stats lines start with text)
    ms = dt.timedelta(milliseconds=1)
    passes = [[r for r in rows if _tt(a) - ms <= _tt(r[0]) <= _tt(b) + ms] for a, b in ivs]                                   # rows per access interval
    lat, _, _ = sc.Children.Item(TARGET).Position.QueryPlanetodetic()
    edge = _edge_range_km(lat, 6678.137, SAT_FOV_FULL_DEG / 2)
    edges_ok = len(passes) == len(ivs) >= 1 and all(
        abs(float(p[0][2]) + (90 - SAT_FOV_FULL_DEG / 2)) < 0.05 and abs(float(p[-1][2]) + (90 - SAT_FOV_FULL_DEG / 2)) < 0.05      # elevation = -(90 - half angle) at cone edge
        and abs(float(p[0][3]) - edge) < 0.1 and abs(float(p[-1][3]) - edge) < 0.1                                                   # independent triangle range
        and all(float(r[3]) >= 300 - 1e-6 for r in p) for p in passes)
    res, f, l, tt = compare_t10(sc)
    t10_file = (D / "T10_AccessComparison.txt").read_text(encoding="utf-8")
    t10_ok = (f, l, tt) == ("Aircraft camera (AC_Camera)",) * 3 and t10_file == t10_text(res, f, l, tt) and _t_first(res)
    return {"first Sat_Camera access = saved animation current time": first is not None and anim["CurrentTime"].startswith(first),
            "animation start/end/step/refresh restored to original": all(anim[k] == v for k, v in ORIG_ANIM.items()),
            "live clock at first access": first is not None and abs(root.CurrentTime - (_tt(first) - _tt(sc.StartTime)).total_seconds()) < 0.01,
            "SatCamera_to_Ica listed + az/el/range present": "SatCamera_to_Ica" in qrs and "Azimuth (deg)" in rpt and "Elevation (deg)" in rpt and "Range (km)" in rpt,
            f"AER edge rows: el -{90 - SAT_FOV_FULL_DEG / 2:g} deg and range {edge:.3f} km (independent geometry), range>=300 km": edges_ok,
            "T10 file matches live recomputation; aircraft first + longest": t10_ok}, {"first": first, "passes": len(passes), "edge_km": round(edge, 3), "T10": (f, l, tt)}


def _tt(s):
    from aircraft_setup import _t
    return _t(s)


def _t_first(res):                      # aircraft first access really is earlier than the satellite's
    ks = list(res)
    return _tt(res[ks[0]]["first_start"]) < _tt(res[ks[1]]["first_start"]) and res[ks[0]]["longest"] > res[ks[1]]["longest"]


if __name__ == "__main__":
    results = {}
    for key, fn in [("Scenario name + 5h window", check_scenario), ("Terrain server off (file)", check_terrain_off),
                    ("Runway shape + 2 deg elevation", check_runway), ("Ica/Paracas coordinates", check_places),
                    ("T1 stored view", check_t1_file), ("T2 Ica lighting in Timeline", check_t2_file), ("T3 Ica_LatLon quick report", check_t3_file),
                    ("P2 aircraft: Great Arc, waypoints, style", check_aircraft_file), ("P2 uav.glb + 100x100 camera", check_model_camera_file),
                    ("T4 FlightSummary.csv", check_t4_csv), ("T5 Aircraft_to_Runway quick report", check_t5_file), ("T6 AircraftView.wmv", check_t6_file),
                    ("P3 satellite orbit (i=15) + cubesat_3u", check_p3_satellite_file), ("P3 Long Description = logged commands", check_p3_long_description),
                    ("P3 Sat_Camera 60 deg Simple Conic", check_p3_sensor_file), ("T8 SatView.bmp", check_t8_file), ("T9 SatCamera_to_Ica entry", check_t9_file)]:
        try:
            ok, why = fn()
        except Exception as e:                            # a missing file is a FAIL, not a crash
            ok, why = False, f"{type(e).__name__}: {e}"
        results[key] = ok
        print(f"{'PASS' if ok else 'FAIL'}  {key:34s} {why}")
    live = live_checks()
    print("live STK checks:", "skipped (STK not running)" if live is None else live)
    liveok = live is not None and all(live.values())

    def st(ok, extra=True):
        return "Verified" if ok and extra else "Blocked"
    track("Scenario", st(results["Scenario name + 5h window"]), "name + 18:54-23:54 in saved .sc and live API")
    # setter was refused (read-only); state is default-off in API and file, GUI checkbox itself never inspected
    track("Terrain", "Needs verification" if results["Terrain server off (file)"] else "Blocked", "off in API+.sc, but setter refused (read-only); GUI checkbox not inspected")
    track("Runway", st(results["Runway shape + 2 deg elevation"]), "4 vertices in order + ElevationAngle 2.0 in API and Runway.at")
    track("Places", st(results["Ica/Paracas coordinates"]), "lat/lon match in API and saved .plc files")
    track("T1 Quake Region view", st(results["T1 stored view"], liveok), "listed by STK, saved in .sc3, round-trip restore checked by snapshot")
    track("T2 Ica lighting timeline", st(results["T2 Ica lighting in Timeline"]), "row+Sunlight/Penumbra/Umbra in saved TimelinePrefs.xml; also seen in Timeline View window")
    track("T3 Ica_LatLon report", st(results["T3 Ica_LatLon quick report"], liveok), "quick report created via toolbar click (QuickReportAdd fails only for the scenario's FIRST quick report); text + saved .sc checked")
    p2 = p3 = p3info = None
    if _stk_pids():
        app = get_app(); root = app.Root                  # keep `app` referenced
        p2 = part2_live(root, root.CurrentScenario)
        p3, p3info = part3_live(root, root.CurrentScenario)
    print("part 2 live checks:", "skipped (STK not running)" if p2 is None else "")
    for k, v in (p2 or {}).items():
        print(f"   {'PASS' if v else 'FAIL'}  {k}")
    print("part 3 live checks:", "skipped (STK not running)" if p3 is None else p3info)
    for k, v in (p3 or {}).items():
        print(f"   {'PASS' if v else 'FAIL'}  {k}")
    p2ok = p2 is not None and all(p2.values())
    p3ok = p3 is not None and all(p3.values())
    ac_ok = results["P2 aircraft: Great Arc, waypoints, style"]
    track("Aircraft", st(ac_ok), "CertAircraft Great Arc in saved .ac")
    track("Waypoints", st(ac_ok), "Runway centroid, Paracas, Ica, Runway in order; turn radius 1000 m; alt 14 km (saved .ac)")
    track("Route style", st(ac_ok), "white (#ffffff), line width 3 (default 2 + 1) in saved .ac")
    track("Model+Attitude", st(ac_ok and results["P2 uav.glb + 100x100 camera"]), "uav.glb in .ac3, AircraftCoordTurn in .ac")
    track("AC_Camera", st(results["P2 uav.glb + 100x100 camera"]), "rectangular, 100 x 100 deg full angles in saved .sn")
    track("T4 FlightSummary.csv", st(results["T4 FlightSummary.csv"]), "exact 7 fields (Time in EpSec); data recomputed independently: azimuth/elevation/speed/cross-track/total time all agree")
    track("T5 Aircraft_to_Runway", st(results["T5 Aircraft_to_Runway quick report"], p2ok), "Access quick report CertAircraft->Runway; text shows 18:54:00-19:41:32.226")
    track("T6 AircraftView.wmv", st(results["T6 AircraftView.wmv"], p2ok), "12.05 s (header+decoder 10-15 s); 241 frames 19:16:23-19:20:23 top-down over Ica: CertAircraft label + route U-turn at Ica seen; Ica label hidden by sensor footprint in ~half the frames; animation period+step restored")
    track("T7 altitude + runway access", st(ac_ok, p2ok), "14.0 km: one unbroken access interval = whole flight (default 10.668 km gave 81.8%)")
    sat_ok = results["P3 satellite orbit (i=15) + cubesat_3u"]
    track("Satellite", st(sat_ok), "CertSatellite via Connect New+SetState: TwoBody, i=15, other elements = STK defaults; saved .sa")
    track("Long Description", st(results["P3 Long Description = logged commands"]), "the two logged Connect commands are in the scenario Long Description (saved .sc)")
    track("Sat model + camera", st(sat_ok and results["P3 Sat_Camera 60 deg Simple Conic"]), "cubesat_3u.glb in .sa3; Sat_Camera Simple Conic half angle 30 = 60 deg full (confirmed by AER edge elevation -60)")
    track("First access + anim time", st(p3 is not None and p3["first Sat_Camera access = saved animation current time"] and p3["live clock at first access"]),
          f"first Sat_Camera->Ica access {p3info and p3info['first']}; animation clock set to it and saved")
    track("T8 SatView.bmp", st(results["T8 SatView.bmp"], p3ok), "SatView.bmp via VO SnapFrame at first access 19:59:17.795: CertSatellite model + label + Sat_Camera cone visible (camera at Ica; frame viewed)")
    track("T9 SatCamera_to_Ica", st(results["T9 SatCamera_to_Ica entry"], p3ok), "AER quick report: az/el/range per pass; edge rows match independent geometry (el -60, range 350.64 km)")
    track("T10 comparison", st(p3 is not None and p3["T10 file matches live recomputation; aircraft first + longest"]), f"aircraft camera first (19:17:01.484 vs 19:59:17.795) and longest (81.519 s vs 47.800 s); file T10_AccessComparison.txt")
    all_files = all((D / n).exists() for n in [SC_FILE.name, SC_FILE.name.replace(".sc", ".sc3"), "Runway.at", "Ica.plc", "Paracas.plc", f"{QR_NAME}.rst", f"{NAME}TimelinePrefs.xml",
                                               f"{AC}.ac", f"{AC}.ac3", f"{CAM}.sn", "FlightSummary.csv", "FlightSummary.rst", "AircraftView.wmv",
                                               f"{SAT}.sa", f"{SAT}.sa3", f"{SAT_CAM}.sn", "SatView.bmp", "T10_AccessComparison.txt"])
    track("Saved", st(all(results.values()) and all_files and p2ok and p3ok), f"{SC_FILE.name} + all object/report/video/image files on disk; all file + live checks PASS")
