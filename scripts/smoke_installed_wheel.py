"""Build artifact acceptance in a temporary venv outside the source checkout."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv must be installed and available on PATH")
    wheel = args.wheel.resolve(strict=True)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    # Windows scanners may briefly retain a newly imported .pyd after child exit.
    # Cleanup contention must not hide the actual installation/assertion result.
    with tempfile.TemporaryDirectory(
        prefix="xhs-wheel-smoke-", ignore_cleanup_errors=True
    ) as directory:
        root = Path(directory)
        venv = root / "env"
        bin_dir = venv / ("Scripts" if sys.platform == "win32" else "bin")
        python = bin_dir / ("python.exe" if sys.platform == "win32" else "python")
        executable = bin_dir / ("xhs.exe" if sys.platform == "win32" else "xhs")
        subprocess.run(
            [uv, "venv", "--python", sys.executable, str(venv)],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [uv, "pip", "install", "--link-mode", "copy", "--python", str(python), str(wheel)],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "from xiaohongshu_tools import XiaohongshuClient; "
                "assert XiaohongshuClient().browser is None",
            ],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
        )
        version = subprocess.run(
            [str(executable), "--version"],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        invalid = subprocess.run(
            [str(executable), "--unknown-private=fixture-secret"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert version.stdout.strip() == "0.1.1"
        assert invalid.returncode == 1 and invalid.stderr == ""
        assert json.loads(invalid.stdout)["error"]["code"] == "invalid_arguments"
        assert "fixture-secret" not in invalid.stdout
    print(
        json.dumps(
            {
                "status": "passed",
                "version": "0.1.1",
                "installedOutsideSource": True,
                "consoleScript": True,
            }
        )
    )


if __name__ == "__main__":
    main()
