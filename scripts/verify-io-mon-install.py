#!/usr/bin/env python3
"""Verify real file capture and child exit propagation through installed io-mon.

No mocks: the child reads and writes real files and exits 7. The unmonitored
control and captured child must produce the same bytes. This follows io-mon's
release smoke contract using Python, already installed by the repository check.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

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
    capture = subprocess.run(["/usr/bin/io-mon", "run", "--depfile", str(depfile),
                              "--"] + child + [str(output)], timeout=30,
                             text=True, capture_output=True)
    if capture.stderr:
        print(capture.stderr, file=sys.stderr)
    assert capture.returncode == 7, capture
    assert control.read_bytes() == output.read_bytes() == b"release-input-captured"
    decoded = subprocess.check_output(["/usr/bin/io-mon", "inspect", str(depfile),
                                       "--format", "json"], timeout=30, text=True)
    evidence = json.loads(decoded)
    assert evidence["completeness"] == "mcComplete", decoded
    assert evidence["summary"]["eventLossCount"] == 0, decoded
    assert str(source) in decoded and str(output) in decoded, decoded
    print("io-mon installed capture, exact child exit, complete depfile and zero event loss: PASS")
