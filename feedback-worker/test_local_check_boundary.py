"""The legacy live check must require explicit consent even in CI."""

import os
import subprocess
import sys
from pathlib import Path


def test_manual_check_refuses_without_opt_in():
    script = Path(__file__).with_name("check_local_services.py")
    result = subprocess.run(
        [sys.executable, str(script)],
        env={"PATH": os.defpath, "CI": "true"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert "--allow-local-writes is required" in result.stderr
    assert "Feedback submitted" not in result.stdout
