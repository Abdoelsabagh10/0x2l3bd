"""Run metadata: creation, resume, and output verification.

``run.json`` is the single mutable metadata file and is updated atomically.
Stage output files are written elsewhere and are never replaced with different
content. Completed stages are never silently reverted to running.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import InputError, RunConflict
from .scope import load_scope
from .util import atomic_write_json, utcnow

STAGES = (
    "subdomains",
    "urls",
    "javascript",
    "content",
    "target",
    "alive",
    "full_recon",
)
STATUSES = ("not_started", "running", "completed", "failed", "skipped")
TERMINAL = ("completed", "skipped")

STAGE_DIRS = ("raw", "processed", "rejected", "logs")

STAGE_REQUIRED: Dict[str, List[str]] = {
    "subdomains": ["processed/subdomains.txt"],
    "urls": [
        "processed/urls.txt",
        "processed/categories/with-parameters.txt",
        "processed/categories/api.txt",
        "processed/categories/static.txt",
        "processed/categories/javascript.txt",
        "processed/categories/other.txt",
        "processed/categories/parameters.txt",
    ],
    "javascript": [
        "processed/endpoints.txt",
        "processed/parameters.txt",
        "processed/hosts.txt",
        "processed/sourcemaps.txt",
        "processed/secret-leads.md",
    ],
    "content": ["processed/content.txt"],
    "target": ["summary.md"],
    "alive": ["processed/alive.txt"],
    "full_recon": [],
}

PROGRAM_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def program_directory(program: str) -> Path:
    """Resolve ``programs/<program>``, failing closed when it is unusable."""

    if not PROGRAM_SLUG.match(program or ""):
        raise InputError("invalid program slug: %r" % program)
    if program == "_template":
        raise InputError("refusing to run against the program template")

    candidates = [Path.cwd() / "programs" / program]
    workspace = Path(__file__).resolve().parents[2]
    fallback = workspace / "programs" / program
    if fallback not in candidates:
        candidates.append(fallback)

    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise InputError("program directory not found: programs/%s" % program)


def runs_directory(program_dir: Path) -> Path:
    return program_dir / "recon" / "runs"


def run_json_path(program_dir: Path, run_id: str) -> Path:
    return runs_directory(program_dir) / run_id / "run.json"


def stage_directory(program_dir: Path, stage: str, run_id: str) -> Path:
    if stage == "full_recon":
        return runs_directory(program_dir) / run_id
    return program_dir / "recon" / stage / run_id


def validate_run_id(run_id: str) -> str:
    if not RUN_ID.match(run_id or ""):
        raise InputError("invalid run ID: %r" % run_id)
    return run_id


def new_run_id(stage: str, directory: Path) -> str:
    """Build ``YYYYMMDD-HHMMSS-<stage>`` and avoid collisions."""

    base = utcnow().replace("-", "").replace(":", "").replace("T", "-").replace("Z", "")
    candidate = "%s-%s" % (base, stage)
    counter = 1
    while (directory / candidate / "run.json").exists():
        counter += 1
        candidate = "%s-%s-%d" % (base, stage, counter)
    return candidate


def _new_stage(now: str) -> dict:
    return {
        "status": "running",
        "attempts": 1,
        "first_started_at": now,
        "last_started_at": now,
        "finished_at": None,
        "resumed": False,
        "outputs": [],
        "logs": [],
        "tools": [],
        "commands": [],
        "error": None,
        "errors": [],
    }


def _new_run(program: str, run_id: str, stage: str, scope, now: str) -> dict:
    return {
        "version": 1,
        "run_id": run_id,
        "program": program,
        "scope_path": scope.path,
        "scope_sha256": scope.sha256,
        "started_at": now,
        "updated_at": now,
        "finished_at": None,
        "resumed": False,
        "targets": [],
        "notes": [],
        "stages": {stage: _new_stage(now)},
    }


def init_run(
    program: str,
    stage: str,
    scope_path: str,
    run_id: Optional[str] = None,
) -> dict:
    """Create or resume a run for one stage."""

    if stage not in STAGES:
        raise InputError("unsupported stage: %r" % stage)
    program_dir = program_directory(program)
    scope = load_scope(scope_path)
    if scope.program != program:
        raise RunConflict(
            "scope program %r does not match --program %r"
            % (scope.program, program)
        )

    directory = runs_directory(program_dir)
    directory.mkdir(parents=True, exist_ok=True)

    resumed = False
    changed = True
    if run_id is None:
        run_id = new_run_id(stage, directory)
    else:
        validate_run_id(run_id)

    metadata_path = run_json_path(program_dir, run_id)
    now = utcnow()

    if metadata_path.is_file():
        try:
            run = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InputError("cannot read run metadata %s: %s" % (metadata_path, exc)) from exc
        if run.get("program") != program:
            raise RunConflict(
                "run %s belongs to program %r, not %r"
                % (run_id, run.get("program"), program)
            )
        if run.get("scope_sha256") != scope.sha256:
            raise RunConflict(
                "scope changed since run %s was created; refusing to resume" % run_id
            )

        stages = run.setdefault("stages", {})
        record = stages.setdefault(stage, _new_stage(now))
        status = record.get("status", "not_started")
        resumed = True
        run["resumed"] = True
        run["updated_at"] = now
        record["resumed"] = True

        if status in TERMINAL:
            # Completed and skipped stages are terminal. Never revert them.
            changed = False
        else:
            record["status"] = "running"
            record["attempts"] = int(record.get("attempts", 0)) + 1
            record["first_started_at"] = record.get("first_started_at") or now
            record["last_started_at"] = now
            record["finished_at"] = None
            if record.get("error"):
                record.setdefault("errors", []).append(record["error"])
                record["error"] = None
    else:
        run = _new_run(program, run_id, stage, scope, now)

    if stage != "full_recon":
        root = stage_directory(program_dir, stage, run_id)
        for name in STAGE_DIRS:
            (root / name).mkdir(parents=True, exist_ok=True)

    atomic_write_json(metadata_path, run)

    return {
        "ok": True,
        "command": "runs init",
        "run_id": run_id,
        "program": program,
        "stage": stage,
        "status": run["stages"][stage].get("status"),
        "scope_sha256": scope.sha256,
        "run_json": str(metadata_path),
        "stage_dir": str(stage_directory(program_dir, stage, run_id)),
        "resumed": resumed,
        "changed": changed,
    }


def verify_run(program: str, run_id: str, stage: str) -> Tuple[dict, int]:
    """Check that a stage produced its required files.

    A non-terminal stage becomes completed on success or failed on failure.
    Terminal stages are reported on but never reverted.
    """

    if stage not in STAGES:
        raise InputError("unsupported stage: %r" % stage)
    program_dir = program_directory(program)
    metadata_path = run_json_path(program_dir, run_id)
    if not metadata_path.is_file():
        raise InputError("run metadata not found: %s" % metadata_path)

    try:
        run = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError("cannot read run metadata %s: %s" % (metadata_path, exc)) from exc

    scope_path = run.get("scope_path")
    if scope_path:
        current = load_scope(scope_path)
        if current.sha256 != run.get("scope_sha256"):
            raise RunConflict(
                "scope changed since run %s was created" % run_id
            )

    record = run.get("stages", {}).get(stage)
    if record is None:
        raise InputError("stage %r is not part of run %s" % (stage, run_id))

    root = stage_directory(program_dir, stage, run_id)
    present: List[str] = []
    missing: List[str] = []
    empty: List[str] = []
    for relative in STAGE_REQUIRED.get(stage, []):
        target = root / relative
        if not target.is_file():
            missing.append(relative)
            continue
        present.append(relative)
        if target.stat().st_size == 0:
            empty.append(relative)

    ok = not missing and not empty
    status = record.get("status", "not_started")
    now = utcnow()
    updated = False

    if status not in TERMINAL:
        record["status"] = "completed" if ok else "failed"
        record["finished_at"] = now
        if ok:
            record["error"] = None
            record["outputs"] = [str(root / item) for item in present]
        else:
            problem = "missing or empty outputs: %s" % ", ".join(missing + empty)
            record["error"] = problem
            record["errors"] = list(record.get("errors", [])) + [problem]
        run["updated_at"] = now
        status = record["status"]
        updated = True
        atomic_write_json(metadata_path, run)

    return (
        {
            "ok": ok,
            "command": "runs verify",
            "run_id": run_id,
            "program": program,
            "stage": stage,
            "status": status,
            "present": present,
            "missing": missing,
            "empty": empty,
            "run_json": str(metadata_path),
            "updated": updated,
        },
        0 if ok else 5,
    )
