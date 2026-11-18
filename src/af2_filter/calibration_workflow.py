import hashlib
import json
import shutil
import sys
import traceback
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter

from workflow import AF2_REVISION, SOURCE, prepare_runtime, run_logged


VERSION = "0.1.0"
ARCHIVE_URL = "https://ndownloader.figshare.com/files/40226533"
ARCHIVE_SHA256 = None  # filled in on the first run and recorded in source.json
RELEASE = "PUBLIC_RELEASE/experimentally_tested/TrkA_binders"
NON_BINDERS = 14
SEED = 0
RECYCLES = 3


def fetch_release(state, log, env):
    """Download the public release once per Colab session and keep the TrkA subtree."""
    release = state / "trka_release"
    if (release / "TrkA_designs.csv").is_file():
        return release
    archive = state / "RFdiffusion_designs.zip"
    if not archive.is_file():
        # HEAD is refused by the signed URL, so a plain GET is the only route.
        run_logged(["curl", "--fail", "--location", "--retry", "3", "--output", archive, ARCHIVE_URL],
                   log, env)
    staging = Path(mkdtemp(prefix="release_", dir=state))
    run_logged(["unzip", "-q", "-o", archive, f"{RELEASE}/*", "-d", staging], log, env)
    (staging / RELEASE).replace(release)
    shutil.rmtree(staging, ignore_errors=True)
    return release


def run(revision):
    root = Path(mkdtemp(prefix="trka88_calibration_", dir="/content"))
    (root / "runtime").mkdir()
    shutil.copytree(SOURCE.parents[1] / "inputs/trka", root / "inputs")
    settings = {"non_binders": NON_BINDERS, "seed": SEED, "recycles": RECYCLES}
    (root / "settings.json").write_text(json.dumps(settings, indent=2))
    source = {"calibration_version": VERSION, "revision": revision, "af2_revision": AF2_REVISION,
              "archive_url": ARCHIVE_URL, "release_path": RELEASE, **settings}
    (root / "source.json").write_text(json.dumps(source, indent=2))
    start = perf_counter()
    try:
        python, upstream, env = prepare_runtime(root)
        release = fetch_release(Path("/content/trka88_af2_v0_3_0"), root / "runtime/release.log", env)
        archive = Path("/content/trka88_af2_v0_3_0/RFdiffusion_designs.zip")
        if archive.is_file():
            with archive.open("rb") as handle:
                source["archive_sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
        source["release_file_count"] = sum(1 for _ in release.rglob("*") if _.is_file())
        (root / "source.json").write_text(json.dumps(source, indent=2))
        run_logged([python, SOURCE / "calibration.py", root, release, upstream],
                   root / "runtime/calibration.log", env)
    except Exception:
        (root / "runtime/failure.txt").write_text(traceback.format_exc())
        print("실패 기록을 ZIP에 저장했습니다.", flush=True)
    finally:
        (root / "runtime/timing.json").write_text(json.dumps({"seconds": perf_counter() - start}))
        print(shutil.make_archive(str(root), "zip", root), flush=True)


if __name__ == "__main__":
    run(sys.argv[1])
