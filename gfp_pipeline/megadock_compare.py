import csv
import json
import os
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

from benchmark import measure_pose
from lightdock_compare import read_pose, write_partner
from run import run_logged


def run_docking(root):
    root = Path(root).resolve()
    settings = json.loads((root / "config/diagnostics.json").read_text())
    config = settings["docking"]
    reference = json.loads((root / "config/reference_minimizer.json").read_text())
    work = root / "docking"
    work.mkdir()
    rng = np.random.default_rng(config["seed"])
    receptor, ligand = work / "receptor.pdb", work / "ligand.pdb"
    write_partner(receptor, reference["target"], "A", rng)
    write_partner(ligand, reference["binder"], "B", rng)
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
    command([binaries / "megadock-gpu", "-R", receptor, "-L", ligand, "-o", output,
             "-r", config["rotations"], "-v", config["voxel_spacing_angstrom"],
             "-N", config["output_poses"], "-f", config["score_function"]], "docking_search")
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
        metrics = measure_pose(target, binder, reference, settings["contact_radius_angstrom"])
        passed = (metrics["target_ca_rmsd_angstrom"] <= settings["max_target_rmsd_angstrom"]
                  and metrics["benchmark_contact_jaccard"] >= settings["min_contact_jaccard"]
                  and not clash["has_clash"])
        rows.append({"rank": rank, "megadock_score": float(record[-1]),
                     "file": str(pose.relative_to(root)), "contact_criterion_passed": passed,
                     **clash, **metrics})
    with (root / "metrics/docking_poses.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"experiment": "minimizer_docking", "backend": "MEGADOCK",
               "revision": config["revision"], "ranked_poses": len(records),
               "poses_evaluated": count, "contact_criterion_passed": sum(row["contact_criterion_passed"] for row in rows),
               "evaluation_scope": "top scoring poses without clustering",
               "clash_rule": f"minimum interchain heavy-atom distance < {config['heavy_atom_clash_distance_angstrom']} angstrom",
               "rows": rows}
    (root / "metrics/diagnostic_summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run_docking(sys.argv[1])
