"""Phase 1: report what this machine can actually do with STK. Read-only apart from starting STK."""
import platform, sys

from stk_common import get_app, connect, track, log

track("Env", "In progress")
app = get_app()
root = app.Root

print("OS         :", platform.platform())
print("Python     :", sys.version.split()[0])
print("STK path   :", app.Path)
print("STK pid    :", app.ProcessID)

# Both documented: Connect "GetLicenses /" and IAgStkObjectRoot.GetLicensingReport() (XML string)
print("\n--- Connect GetLicenses / ---")
for line in connect(root, "GetLicenses /"):
    print(line)
print("\n--- Root.GetLicensingReport() ---")
print(root.GetLicensingReport())

track("Env", "Needs verification", "license output printed, review manually")
log.info("environment_check done")
