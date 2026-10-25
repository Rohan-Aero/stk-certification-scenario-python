"""Shared helpers: attach-or-start STK, Connect wrapper, task tracker, logging."""
import csv, json, logging, pathlib, subprocess, time

from agi.stk13.stkdesktop import STKDesktop

HERE = pathlib.Path(__file__).parent
TRACKER = HERE / "tracker.json"
STATUSES = ("Not started", "In progress", "Needs verification", "Verified", "Blocked")
TASKS = ("Env", "Scenario", "Terrain", "Runway", "Places", "T1 Quake Region view",
         "T2 Ica lighting timeline", "T3 Ica_LatLon report", "Saved")

logging.basicConfig(filename=HERE / "stk_run.log", level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stk")


def _stk_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AgUiApplication.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return [int(r[1]) for r in csv.reader(out.splitlines()) if len(r) > 1 and r[0] == "AgUiApplication.exe"]


def get_app():
    """Attach to the single running STK by pid (start one if none). More than one -> refuse."""
    pids = _stk_pids()
    if len(pids) > 1:
        raise RuntimeError(f"{len(pids)} STK instances running {pids}; close extras so the target is unambiguous")
    if not pids:
        log.info("no running STK, starting one")
        return STKDesktop.StartApplication(visible=True, userControl=True)
    app = STKDesktop.AttachToApplication(pid=pids[0])
    assert app.ProcessID == pids[0], f"attached to {app.ProcessID}, expected {pids[0]}"
    return app


def connect(root, cmd):
    """Run a Connect command, log it, return result lines (raises on STK error)."""
    log.info("CONNECT> %s", cmd)
    res = root.ExecuteCommand(cmd)
    return [res.Item(i) for i in range(res.Count)]


def track(task, status, note=""):
    assert status in STATUSES, status
    data = json.loads(TRACKER.read_text()) if TRACKER.exists() else {t: {"status": "Not started", "note": ""} for t in TASKS}
    data[task] = {"status": status, "note": note, "at": time.strftime("%H:%M:%S")}
    TRACKER.write_text(json.dumps(data, indent=2))
    log.info("TRACK %s -> %s %s", task, status, note)


if __name__ == "__main__":  # self-check: tracker rejects bad status, accepts good
    try:
        track("Env", "Done")
    except AssertionError:
        pass
    else:
        raise SystemExit("tracker accepted an invalid status")
    print("stk_common ok")
