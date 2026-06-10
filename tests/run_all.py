"""Run every test file in this directory. The one entry point for CI and
contributors: `python tests/run_all.py`. Exits non-zero on any failure.

Each test_*.py is executed as its own process (they are self-running harnesses
with their own __main__ blocks), so one file's import-time environment tweaks
can never leak into another.
"""

import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

env = dict(os.environ)
# CI and local runs must be deterministic: no model loads, no API calls.
env.setdefault("MYPM_NO_SEMANTIC", "1")
env.setdefault("MYPM_NO_LLM", "1")

failed = []
for path in sorted(glob.glob(os.path.join(HERE, "test_*.py"))):
    name = os.path.basename(path)
    proc = subprocess.run([sys.executable, path], env=env,
                          capture_output=True, text=True)
    tail = (proc.stdout.strip().splitlines() or ["(no output)"])[-1]
    status = "ok" if proc.returncode == 0 else "FAIL"
    print(f"{status:4} {name:24} {tail}")
    if proc.returncode != 0:
        failed.append(name)
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)

if failed:
    print(f"\n{len(failed)} file(s) failed: {', '.join(failed)}")
    sys.exit(1)
print("\nall test files passed.")
