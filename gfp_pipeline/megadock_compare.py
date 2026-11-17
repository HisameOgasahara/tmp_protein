import csv
import json
import os
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

from benchmark import measure_pose, pose_failure_reasons, recovery_criteria
from docking_selection import rank_docking_candidates
from lightdock_compare import read_pose, write_partner
from run import run_logged


def read_score_components(path):
    with path.open(newline="") as handle:
        rows = csv.DictReader(handle, skipinitialspace=True)
        scores = [
            {"rank": int(row["Rank"]), "total": float(row["total"]),
             "rpsc": float(row["rPSC"]), "electrostatic": float(row["ELEC "]),
             "receptor_ace": float(row["RecACE"])}
            for row in rows if row["Rank"].strip() in {"1", "2"}
        ]
    if [row["rank"] for row in scores] != [1, 2]:
        raise ValueError("MEGADOCK detail output is missing ranks 1 and 2.")
    return scores


def candidate_contacts(target, binder, indices, radius):
    distances = np.linalg.norm(target[indices, None] - binder[None], axis=2)
    return int((distances <= radius).any(axis=1).sum())


def run_docking(root, experiment="minimizer_docking", candidate=None):
    root = Path(root).resolve()
    settings = json.loads((root / "config/diagnostics.json").read_text())
    config = settings["docking"]
    control = experiment.removesuffix("_docking")
    reference = (candidate["reference"] if candidate is not None else
                 json.loads((root / f"config/reference_{control}.json").read_text()))
    binder_input = reference["binder"]
    if control == "enhancer":
        binder_input = json.loads((root / "config/predicted_binder.json").read_text())
    work = root / "docking"
    work.mkdir()
    rng = np.random.default_rng(config["seed"])
    receptor, ligand = work / "receptor.pdb", work / "ligand.pdb"
    write_partner(receptor, reference["target"], "A", rng)
    write_partner(ligand, binder_input, "B", rng)
    binaries = Path(os.environ["MEGADOCK_BIN"])
    env = dict(os.environ)

    def command(arguments, label):
        start = perf_counter()
        status = "failed"
        try:
            run_logged(arguments, root / f"runtime/{label}.log", env, cwd=work)
            status = "success"
        finally:
            with (root / "runtime/timings.jsonl").open("a") as handle:
                handle.write(json.dumps({"model": "MEGADOCK", "operation": label,
                                         "status": status, "seconds": perf_counter() - start}) + "\n")

    output = work / "dock.out"
    print("MEGADOCK GPU search started", flush=True)
    arguments = [binaries / "megadock-gpu", "-R", receptor, "-L", ligand, "-o", output,
                 "-r", config["rotations"], "-v", config["voxel_spacing_angstrom"],
                 "-N", config["output_poses"], "-f", config["score_function"]]
    if control == "minimizer" and candidate is None:
        arguments.append("-O")
    command(arguments, "docking_search")
    # MEGADOCK writes four header lines followed by seven fields per ranked pose.
    records = [line.split() for line in output.read_text().splitlines()[4:] if line.strip()]
    if not records or any(len(record) != 7 for record in records):
        raise RuntimeError("Invalid or empty MEGADOCK ranking output")
    count = min(config["top_poses"], len(records))
    print(f"MEGADOCK GPU search complete; evaluating {count} poses", flush=True)
    receptor_lines = [line for line in receptor.read_text().splitlines() if line.startswith("ATOM")]
    rows = []
    for rank, record in enumerate(records[:count], 1):
        ligand_pose = work / f"ligand_{rank}.pdb"
        command([binaries / "decoygen", ligand_pose, ligand, output, rank], "docking_generate")
        ligand_lines = [line for line in ligand_pose.read_text().splitlines() if line.startswith("ATOM")]
        pose = root / "structures" / f"top_{rank}.pdb"
        pose.write_text("\n".join([*receptor_lines, "TER", *ligand_lines, "TER", "END", ""]))
        target, binder, clash = read_pose(pose, reference, config["heavy_atom_clash_distance_angstrom"])
        if candidate is None:
            metrics = measure_pose(target, binder, reference, settings["contact_radius_angstrom"])
            failures = pose_failure_reasons({**metrics, **clash}, settings)
        else:
            indices = candidate["hotspot_indices"]
            metrics = {"hotspot_contacts": candidate_contacts(target, binder, indices, settings["contact_radius_angstrom"]),
                       "hotspot_sites": len(indices)}
            failures = []
            if metrics["hotspot_contacts"] < candidate["minimum_hotspot_contacts"]:
                failures.append("insufficient_hotspot_contacts")
            if clash["has_clash"]:
                failures.append("clash")
        passed = not failures
        rows.append({"rank": rank, "megadock_score": float(record[-1]),
                     "file": str(pose.relative_to(root)), "contact_criterion_passed": passed, "pose_failure_reasons": failures,
                     **clash, **metrics})
    ranked, selection = rank_docking_candidates(rows, config["heavy_atom_clash_distance_angstrom"])
    for row in rows:
        row.update(ranked[row["rank"]])
    with (root / "metrics/docking_poses.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"experiment": experiment, "recovery_criteria": recovery_criteria(settings), "backend": "MEGADOCK",
               "revision": config["revision"], "ranked_poses": len(records),
               "poses_evaluated": count, "contact_criterion_passed": sum(row["contact_criterion_passed"] for row in rows),
               "evaluation_scope": "top scoring poses without clustering",
               "clash_rule": f"minimum interchain heavy-atom distance < {config['heavy_atom_clash_distance_angstrom']} angstrom",
               "candidate_selection": selection, "rows": rows}
    if candidate is not None:
        summary.pop("recovery_criteria")
        summary["minimum_hotspot_contacts"] = candidate["minimum_hotspot_contacts"]
    if control == "minimizer" and candidate is None:
        summary["score_components_top_two"] = read_score_components(output.with_suffix(".csv"))
    (root / "metrics/diagnostic_summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    if len(sys.argv) == 4:
        run_docking(sys.argv[1], sys.argv[2], json.loads(Path(sys.argv[3]).read_bytes()))
    else:
        run_docking(*sys.argv[1:])
