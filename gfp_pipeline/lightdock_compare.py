import csv
import json
import os
import shutil
import sys
from pathlib import Path
from time import perf_counter

import numpy as np

from benchmark import measure_pose
from residues import AA
from run import run_logged


def write_partner(path, reference, chain, rng):
    records = [row for row in reference["atoms"] if row["atom"] != "OXT" and not row["atom"].startswith("H")]
    coords = np.array([row["coord"] for row in records], dtype=float)
    coords -= coords.mean(axis=0)
    rotation, _ = np.linalg.qr(rng.normal(size=(3, 3)))
    rotation[:, -1] *= np.linalg.det(rotation)
    coords = coords @ rotation
    names = {value: key for key, value in AA.items()}
    lines = []
    for serial, (row, point) in enumerate(zip(records, coords, strict=True), 1):
        name = row["atom"]
        residue = names[reference["sequence"][row["index"]]]
        lines.append(f"ATOM  {serial:5d} {name:^4s} {residue:3s} {chain}{row['index'] + 1:4d}    "
                     f"{point[0]:8.3f}{point[1]:8.3f}{point[2]:8.3f}{1.0:6.2f}{0.0:6.2f}          {name[0]:>2s}")
    path.write_text("\n".join([*lines, "TER", "END", ""]), encoding="utf-8")


def read_pose(path, reference, clash_distance):
    arrays = {chain: np.full((len(reference[name]["sequence"]), 3), np.nan)
              for chain, name in (("A", "target"), ("B", "binder"))}
    heavy = {chain: [] for chain in arrays}
    for line in path.read_text().splitlines():
        if not line.startswith("ATOM") or line[21] not in arrays:
            continue
        chain = line[21]
        name = line[12:16].strip()
        point = [float(line[start:start + 8]) for start in (30, 38, 46)]
        if name == "CA":
            index = int(line[22:26]) - 1
            if index < 0 or index >= len(arrays[chain]):
                raise ValueError("LightDock changed reference residue numbering.")
            arrays[chain][index] = point
        if not name.startswith("H"):
            heavy[chain].append(point)
    if not all(heavy.values()):
        raise ValueError("LightDock pose is missing a partner chain.")
    from scipy.spatial import cKDTree
    nearest, _ = cKDTree(heavy["A"]).query(np.array(heavy["B"]))
    minimum = float(nearest.min())
    return arrays["A"], arrays["B"], {
        "has_clash": minimum < clash_distance,
        "min_interchain_heavy_atom_distance_angstrom": minimum,
    }


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
    scripts = Path(sys.executable).parent
    env = dict(os.environ)

    def command(script, arguments, label, cwd=work):
        start = perf_counter()
        status = "failed"
        try:
            run_logged([sys.executable, scripts / script, *arguments], root / f"runtime/{label}.log", env, cwd=cwd)
            status = "success"
        finally:
            with (root / "runtime/timings.jsonl").open("a") as handle:
                handle.write(json.dumps({"model": "LightDock", "operation": label,
                                         "status": status, "seconds": perf_counter() - start}) + "\n")

    arguments = [receptor, ligand, "--noxt", "--noh", "--now", "-g", config["glowworms"],
                 "--seed_points", config["seed"]]
    if config["swarms"] is not None:
        arguments.extend(["-s", config["swarms"]])
    command("lightdock3_setup.py", arguments, "docking_setup")
    swarms = sorted(work.glob("swarm_*"), key=lambda path: int(path.name.split("_")[-1]))
    if not swarms or not (work / "setup.json").is_file():
        raise RuntimeError("LightDock setup did not produce swarms.")
    command("lightdock3.py", ["setup.json", config["steps"], "-s", config["scoring"],
                              "-sg", config["seed"], "-c", os.cpu_count() or 1], "docking_search")
    output_name = f"gso_{config['steps']}.out"
    for swarm in swarms:
        if not (swarm / output_name).is_file():
            raise RuntimeError(f"Missing final docking output: {swarm.name}")
        command("lgd_generate_conformations.py", [receptor, ligand, output_name, config["glowworms"],
                                                   "--setup", work / "setup.json"],
                f"generate_{swarm.name}", cwd=swarm)
        command("lgd_cluster_bsas.py", [output_name], f"cluster_{swarm.name}", cwd=swarm)
        if not (swarm / "cluster.repr").is_file():
            raise RuntimeError(f"LightDock clustering failed: {swarm.name}")
        # Final GSO coordinates and cluster representatives retain every pose;
        # regenerate PDBs on demand instead of retaining thousands of duplicates.
        for path in swarm.glob("lightdock_*.pdb"):
            if path.resolve().parent != swarm.resolve():
                raise ValueError("Unexpected intermediate pose path.")
            path.unlink()
    command("lgd_rank.py", [len(swarms), config["steps"]], "docking_rank")
    ranking = work / "rank_by_scoring.list"
    ranked_lines = ranking.read_text().splitlines()[1:]
    count = min(config["top_poses"], len(ranked_lines))
    if not count:
        raise RuntimeError("LightDock ranking has no poses.")
    command("lgd_top.py", [receptor, ligand, ranking, count, "--setup", work / "setup.json"], "docking_top")
    rows = []
    for rank in range(1, count + 1):
        path = work / f"top_{rank}.pdb"
        target, binder, clash = read_pose(path, reference, config["heavy_atom_clash_distance_angstrom"])
        metrics = measure_pose(target, binder, reference, settings["contact_radius_angstrom"])
        destination = root / "structures" / path.name
        shutil.move(path, destination)
        passed = (metrics["target_ca_rmsd_angstrom"] <= settings["max_target_rmsd_angstrom"]
                  and metrics["benchmark_contact_jaccard"] >= settings["min_contact_jaccard"]
                  and not clash["has_clash"])
        rows.append({"rank": rank, "lightdock_score": float(ranked_lines[rank - 1].split()[-1]),
                     "file": str(destination.relative_to(root)), "contact_criterion_passed": passed,
                     **clash, **metrics})
    with (root / "metrics/docking_poses.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"experiment": "minimizer_docking", "swarms": len(swarms), "ranked_representatives": len(ranked_lines),
               "poses_evaluated": count, "contact_criterion_passed": sum(row["contact_criterion_passed"] for row in rows),
               "evaluation_scope": "top scoring cluster representatives only",
               "clash_rule": f"minimum interchain heavy-atom distance < {config['heavy_atom_clash_distance_angstrom']} angstrom",
               "rows": rows}
    (root / "metrics/diagnostic_summary.json").write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    run_docking(sys.argv[1])
