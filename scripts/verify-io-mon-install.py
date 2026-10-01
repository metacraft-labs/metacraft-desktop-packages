#!/usr/bin/env python3
"""Verify real file capture and child exit propagation through installed io-mon.

No mocks: the child reads and writes real files and exits 7. The unmonitored
control and captured child must produce the same bytes. This follows io-mon's
release smoke contract using Python, already installed by the repository check.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

CLI = os.environ.get("IO_MON_CLI", "/usr/bin/io-mon")

if len(sys.argv) > 1 and sys.argv[1] == "probe":
    Path(sys.argv[3]).write_bytes(Path(sys.argv[2]).read_bytes() + b"-captured")
    sys.exit(7)

with tempfile.TemporaryDirectory(prefix="io-mon-install-") as directory:
    directory = Path(directory)
    source, output = directory / "input.txt", directory / "output.txt"
    control, depfile = directory / "control.txt", directory / "capture.rdep"
    source.write_bytes(b"release-input")
    child = [sys.executable, str(Path(__file__).resolve()), "probe", str(source)]
    assert subprocess.run(child + [str(control)], timeout=30).returncode == 7
    capture = subprocess.run([CLI, "run", "--depfile", str(depfile),
                              "--"] + child + [str(output)], timeout=30,
                             text=True, capture_output=True)
    if capture.stderr:
        print(capture.stderr, file=sys.stderr)
    assert capture.returncode == 7, capture
    assert control.read_bytes() == output.read_bytes() == b"release-input-captured"
    decoded = subprocess.check_output([CLI, "inspect", str(depfile),
                                       "--format", "json"], timeout=30, text=True)
    evidence = json.loads(decoded)
    assert evidence["completeness"] == "mcComplete", decoded
    assert evidence["summary"]["eventLossCount"] == 0, decoded
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for child in value.values():
                yield from strings(child)
        elif isinstance(value, list):
            for child in value:
                yield from strings(child)

    def normalized(value):
        return os.path.normcase(os.path.normpath(value))

    paths = {normalized(value) for value in strings(evidence)}
    assert normalized(str(source)) in paths and normalized(str(output)) in paths, decoded
    print("io-mon installed capture, exact child exit, complete depfile and zero event loss: PASS")
