"""Builds the program that runs in the sandbox and parses its results."""
from __future__ import annotations

import base64
import json
import re
import secrets

from .exercises import BY_ID
from .sandbox import execute

HARNESS = '''
import base64 as __b64, json as __json, traceback as __tb
__ns = {"__name__": "solution"}
__load_error = None
try:
    exec(compile(__b64.b64decode("%(src)s").decode(), "solution.py", "exec"), __ns)
except BaseException as __e:
    __load_error = "".join(__tb.format_exception_only(type(__e), __e)).strip()
__test_ns = dict(__ns)
exec(compile(__b64.b64decode("%(tests)s").decode(), "tests.py", "exec"), __test_ns)
__results = []
for __name in %(names)s:
    if __load_error:
        __results.append({"name": __name, "passed": False, "error": "Code failed to load: " + __load_error})
        continue
    try:
        __test_ns[__name]()
        __results.append({"name": __name, "passed": True, "error": ""})
    except AssertionError as __e:
        __results.append({"name": __name, "passed": False, "error": "AssertionError: " + str(__e)})
    except BaseException as __e:
        __results.append({"name": __name, "passed": False,
                          "error": "".join(__tb.format_exception_only(type(__e), __e)).strip()[:500]})
print("%(marker)s" + __json.dumps(__results))
'''


def build_program(code: str, tests: str, marker: str) -> str:
    names = re.findall(r"^def (test_\w+)\(", tests, re.M)
    return HARNESS % {
        "src": base64.b64encode(code.encode()).decode(),
        "tests": base64.b64encode(tests.encode()).decode(),
        "names": json.dumps(names),
        "marker": marker,
    }


def run_exercise(exercise_id: str, code: str) -> dict:
    ex = BY_ID[exercise_id]
    marker = f"@@RESULTS-{secrets.token_hex(8)}@@"
    res = execute(build_program(code, ex["tests"], marker))
    tests = []
    for line in res.stdout.splitlines():
        if line.startswith(marker):
            tests = json.loads(line[len(marker):])
    user_stdout = "\n".join(l for l in res.stdout.splitlines() if not l.startswith(marker))
    passed = sum(t["passed"] for t in tests)
    return {
        "exercise": exercise_id, "backend": res.backend, "duration_ms": res.duration_ms,
        "tests": tests, "passed": passed, "total": len(tests),
        "score": round(100 * passed / len(tests), 1) if tests else 0.0,
        "stdout": user_stdout[-4000:], "stderr": res.stderr[-4000:],
        "harness_error": None if tests else "No test results were produced (timeout, crash or output tampering).",
    }
