import csv
import json
import shutil
import sys
from pathlib import Path
from tempfile import mkdtemp

import numpy as np
from Bio.PDB import MMCIFParser, PDBIO

from benchmark import build_chain_reference, reference_ca
from megadock_compare import candidate_contacts
from megadock_runtime import prepare_megadock
from run import SOURCE, run_logged


VERSION = "0.1.0"
RUN02 = SOURCE.parent / "results/02_gfp_binder_3md9l1qe"


def load_candidates():
    target = json.loads((RUN02 / "config/target.json").read_bytes())
    designs = json.loads((RUN02 / "config/designs.json").read_bytes())
    with (RUN02 / "metrics/complexes.csv").open(newline="") as handle:
        baseline = {row["id"]: row for row in csv.DictReader(handle)}
    target_reference = build_chain_reference(
        (RUN02 / "structures/target.pdb").read_text().splitlines(), target["chain"], target["sequence"]
    )
    parser = MMCIFParser(QUIET=True)
    from io import StringIO

    for design in designs:
        name = design["id"]
        structure = parser.get_structure(name, RUN02 / baseline[name]["file"])
        output = StringIO()
        writer = PDBIO()
        writer.set_structure(structure)
        writer.save(output)
        lines = output.getvalue().splitlines()
        binder = build_chain_reference(lines, "B", design["sequence"])
        predicted_target = build_chain_reference(lines, "A", target["sequence"])
        target_ca = np.full((len(target["sequence"]), 3), np.nan)
        indices, coordinates = reference_ca(predicted_target)
        target_ca[indices] = coordinates
        yield name, {
            "reference": {"target": target_reference, "binder": binder},
            "hotspot_indices": target["hotspot_indices"],
            "minimum_hotspot_contacts": 2,
            "rf3_hotspot_contacts": candidate_contacts(
                target_ca, reference_ca(binder)[1], target["hotspot_indices"], 8.0
            ),
        }


def run_validation(revision):
    root = Path(mkdtemp(prefix="gfp_candidate_validation_", dir="/content"))
    print(root, flush=True)
    candidates = list(load_candidates())
    settings = json.loads((SOURCE / "diagnostic_experiments.json").read_bytes())
    results = []
    for name, candidate in candidates:
        directory = root / name
        for folder in ("config", "runtime", "metrics", "structures"):
            (directory / folder).mkdir(parents=True)
        config = directory / "config/candidate.json"
        config.write_text(json.dumps(candidate, indent=2))
        (directory / "config/diagnostics.json").write_text(json.dumps(settings, indent=2))
        python, env = prepare_megadock(directory, settings)
        print(f"MEGADOCK: {name}", flush=True)
        run_logged([python, SOURCE / "megadock_compare.py", directory, name, config],
                   directory / "runtime/docking.log", env)
        diagnostic = json.loads((directory / "metrics/diagnostic_summary.json").read_bytes())
        selected = next((row for row in diagnostic["rows"] if row["selected"]), None)
        results.append({
            "id": name,
            "rf3_hotspot_contacts": candidate["rf3_hotspot_contacts"],
            "docking_selected_rank": selected["rank"] if selected else None,
            "docking_hotspot_contacts": selected["hotspot_contacts"] if selected else None,
            "docking_passed": bool(selected and selected["contact_criterion_passed"]),
            "docking_poses_meeting_both_criteria": diagnostic["contact_criterion_passed"],
        })
    (root / "source.json").write_text(json.dumps({
        "revision": revision, "validation_version": VERSION, "reference_run": RUN02.name
    }, indent=2))
    (root / "candidate_summary.json").write_text(json.dumps(results, indent=2))
    print(shutil.make_archive(str(root), "zip", root_dir=root), flush=True)


if __name__ == "__main__":
    run_validation(sys.argv[1])
