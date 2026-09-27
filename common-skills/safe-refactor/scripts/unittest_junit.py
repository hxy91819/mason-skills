#!/usr/bin/env python3
"""Run local Python unittest discovery and write fresh JUnit (stdlib only)."""
import argparse
import os
from pathlib import Path
import sys
import time
import tempfile
import unittest
import xml.etree.ElementTree as ET


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []
        self.active = {}

    def startTest(self, test):
        super().startTest(test)
        row = {"name": test.id(), "start": time.monotonic(), "duration": 0.0, "issues": []}
        self.rows.append(row)
        self.active[id(test)] = row

    def _row(self, test):
        # setUpClass/tearDownClass errors may not have a preceding startTest.
        if id(test) not in self.active:
            row = {"name": test.id(), "start": time.monotonic(), "duration": 0.0, "issues": []}
            self.rows.append(row)
            self.active[id(test)] = row
        return self.active[id(test)]

    def stopTest(self, test):
        self.active[id(test)]["duration"] = time.monotonic() - self.active[id(test)]["start"]
        super().stopTest(test)

    def addFailure(self, test, err):
        self._row(test)["issues"].append(("failure", self._exc_info_to_string(err, test)))
        super().addFailure(test, err)

    def addError(self, test, err):
        self._row(test)["issues"].append(("error", self._exc_info_to_string(err, test)))
        super().addError(test, err)

    def addSkip(self, test, reason):
        self._row(test)["issues"].append(("skipped", reason))
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self._row(test)["issues"].append(("skipped", "expected failure: " + self._exc_info_to_string(err, test)))
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self._row(test)["issues"].append(("failure", "unexpected success"))
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            kind = "failure" if issubclass(err[0], test.failureException) else "error"
            self._row(test)["issues"].append((kind, str(subtest) + "\n" + self._exc_info_to_string(err, test)))
        super().addSubTest(test, subtest, err)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--start", default="tests")
    p.add_argument("--pattern", default="test*.py")
    p.add_argument("--top")
    args = p.parse_args(argv)
    output = Path(args.output)
    if output.exists() or output.is_symlink():
        p.error("output already exists; choose a fresh report path")
    # Avoid timestamp/size-valid bytecode from a previous Git revision. Never delete
    # user caches; redirect Python's cache lookup into a fresh, owned directory.
    previous_prefix, previous_write = sys.pycache_prefix, sys.dont_write_bytecode
    with tempfile.TemporaryDirectory(prefix="refactor-unittest-cache-") as cache:
        sys.pycache_prefix, sys.dont_write_bytecode = cache, True
        try:
            suite = unittest.defaultTestLoader.discover(args.start, pattern=args.pattern, top_level_dir=args.top)
            result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
        finally:
            sys.pycache_prefix, sys.dont_write_bytecode = previous_prefix, previous_write
    root = ET.Element("testsuite", name="unittest", tests=str(len(result.rows)),
                      failures=str(len(result.failures) + len(result.unexpectedSuccesses)),
                      errors=str(len(result.errors)), skipped=str(len(result.skipped)))
    for row in result.rows:
        cls, _, name = row["name"].rpartition(".")
        case = ET.SubElement(root, "testcase", classname=cls, name=name, time="%.6f" % row["duration"])
        for kind, detail in row["issues"]:
            ET.SubElement(case, kind).text = detail
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    return 0 if result.wasSuccessful() and result.testsRun > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
