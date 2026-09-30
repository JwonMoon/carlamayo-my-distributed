"""Per-run output directory: ``runs/<timestamp>_<loop>_v<version>[_<mode>][_<tag>]/``.

Every launcher invocation gets its own folder so re-runs never overwrite each other.
The folder name is the *run id*; it is also sent to the remote inference server (as
``ClientMeta.run_id``) so both hosts write their profiles under the same name.

Contents written here: ``args.json`` (CLI arguments, git sha, host, start time) and
``log.txt`` (a copy of stdout). Loops put their videos and profile CSVs next to them.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_RUNS_ROOT = "runs"
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_component(text: str) -> str:
    """Make ``text`` safe for a folder name (keeps letters, digits, ``.``, ``_``, ``-``)."""
    cleaned = _SAFE.sub("-", str(text).strip()).strip("-_.")
    return cleaned


def build_run_id(
    loop: str,
    version: str,
    mode: str | None = None,
    tag: str | None = None,
    now: datetime | None = None,
) -> str:
    """Return ``YYYYMMDD-HHMMSS_<loop>_v<version>[_<mode>][_<tag>]``."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    parts = [stamp, sanitize_component(loop), f"v{sanitize_component(version)}"]
    if mode:
        parts.append(sanitize_component(mode))
    if tag:
        tag = sanitize_component(tag)
        if tag:
            parts.append(tag)
    return "_".join(parts)


def git_sha(cwd: str | os.PathLike | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=cwd, capture_output=True, text=True, check=False, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


class TeeStdout:
    """Duplicate everything written to stdout into a file (``log.txt``)."""

    def __init__(self, path: str | os.PathLike):
        self._file = open(path, "a", encoding="utf-8")  # noqa: SIM115 - lives until close()
        self._stdout = sys.stdout
        sys.stdout = self

    def write(self, text):
        self._stdout.write(text)
        self._file.write(text)

    def flush(self):
        self._stdout.flush()
        self._file.flush()

    def isatty(self):
        return getattr(self._stdout, "isatty", lambda: False)()

    def fileno(self):
        return self._stdout.fileno()

    def close(self):
        if sys.stdout is self:
            sys.stdout = self._stdout
        self._file.close()


class RunDir:
    """One run's output folder."""

    def __init__(self, path: str | os.PathLike, run_id: str):
        self.path_ = Path(path)
        self.run_id = run_id
        self._tee: TeeStdout | None = None

    @classmethod
    def create(
        cls,
        loop: str,
        version: str,
        mode: str | None = None,
        tag: str | None = None,
        root: str | os.PathLike = DEFAULT_RUNS_ROOT,
        now: datetime | None = None,
    ) -> RunDir:
        """Create ``<root>/<run_id>/`` (adding ``-2``, ``-3``... if the name is taken)."""
        root = Path(root)
        base_id = build_run_id(loop, version, mode, tag, now=now)
        run_id, suffix = base_id, 1
        while (root / run_id).exists():
            suffix += 1
            run_id = f"{base_id}-{suffix}"
        (root / run_id).mkdir(parents=True, exist_ok=False)
        return cls(root / run_id, run_id)

    def __str__(self) -> str:
        return str(self.path_)

    def __fspath__(self) -> str:
        return str(self.path_)

    def path(self, name: str | os.PathLike) -> str:
        """Return ``name`` inside the run folder, unless ``name`` already has a directory."""
        name = str(name)
        if os.path.isabs(name) or os.path.dirname(name):
            return name
        return str(self.path_ / name)

    def write_args(self, args: Any, extra: dict[str, Any] | None = None) -> str:
        """Write ``args.json`` with the parsed CLI namespace plus run metadata."""
        payload = {
            "run_id": self.run_id,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "hostname": socket.gethostname(),
            "git_sha": git_sha(),
            "argv": list(sys.argv),
            "args": {
                k: v for k, v in vars(args).items()
                if k != "run_dir" and _is_jsonable(v)
            },
        }
        if extra:
            payload.update(extra)
        out = self.path_ / "args.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return str(out)

    def start_log(self, name: str = "log.txt") -> TeeStdout:
        """Mirror stdout into ``<run>/log.txt`` until :meth:`close` is called."""
        if self._tee is None:
            self._tee = TeeStdout(self.path_ / name)
        return self._tee

    def close(self) -> None:
        if self._tee is not None:
            self._tee.close()
            self._tee = None

    def write_json(self, name: str, data: Any) -> str:
        out = self.path_ / name
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return str(out)


def _is_jsonable(value: Any) -> bool:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


def resolve_output_video(args: Any, default_name: str) -> str:
    """Where a loop should write its video.

    ``--output-video`` wins; a bare filename lands inside the run folder, a path with a
    directory is used as-is. Without a run folder (direct ``run()`` calls from tests or
    other scripts) the current directory is used, matching upstream behaviour.
    """
    name = getattr(args, "output_video", None) or default_name
    run_dir = getattr(args, "run_dir", None)
    if run_dir is None:
        return name
    return run_dir.path(name)


def elapsed_since(start: float) -> float:
    return time.perf_counter() - start
