"""Score the experimentally labelled public designs with the calibrated filter.

The public release holds 95 TrkA designs with an experimental binding label,
6 of which bound. Running them all through the same AF2 initial-guess filter
shows what the pass line actually separates, which a single reproduction cannot.

All selected designs are prepared first and handed to the upstream predictor in
one call, so the model is loaded once rather than per design.
"""

import argparse
import csv
import json
import runpy
import sys
from pathlib import Path

import numpy as np

from compare import design_reference, pose_rmsd
from target_sidechains import complex_with_target_sidechains


# Watson et al. 2023, Extended Data Fig. 8 legend: "In silico success is defined
# in line with current best practice: AF2 pLDDT of the monomer > 80, AF2
# interaction pAE < 10, AF2 r.m.s.d. monomer vs design < 1 A."
PAE_PASS = 10.0
PLDDT_PASS = 80.0
RMSD_PASS = 1.0


def read_sequences(path):
    """The release fasta alternates a bare name line and a sequence line."""
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    return {lines[i].lstrip(">"): lines[i + 1] for i in range(0, len(lines) - 1, 2)}


def select(rows, non_binders, seed):
    """Every binder, plus a deterministic sample of non-binders."""
    binders = [row for row in rows if row["Binder"] == "True"]
    others = [row for row in rows if row["Binder"] != "True"]
    generator = np.random.default_rng(seed)
    picked = [others[i] for i in sorted(generator.choice(len(others), size=min(non_binders, len(others)),
                                                         replace=False))]
    return binders + picked


def prepare(record, release, reference, directory):
    """Write one AF2-ready complex: published sequence on the design backbone."""
    import pyrosetta
    from pyrosetta.toolbox.mutants import mutate_residue

    design_path = release / "rfdiffusion" / f"{record['design']}.pdb"
    grafted = directory / f"{record['design']}_grafted.pdb"
    grafted.write_text(complex_with_target_sidechains(design_path, reference))
    pose = pyrosetta.pose_from_pdb(str(grafted))
    binder = record["sequence"]
    if pose.chain_end(1) != len(binder):
        raise ValueError(f"{record['design']}: chain 1 has {pose.chain_end(1)} residues, "
                         f"sequence has {len(binder)}.")
    for index, residue in enumerate(binder, 1):
        mutate_residue(pose, index, residue)
    target = pose.chain_sequence(2)
    if pose.sequence() != binder + target:
        raise ValueError(f"{record['design']}: prepared sequence does not match.")
    out = directory / "prepared" / f"{record['design']}.pdb"
    pose.dump_pdb(str(out))
    return out, target, grafted


def check_sidechains(path, binder_length):
    """Fail loudly if the target went in without sidechains."""
    from Bio.PDB import PDBParser

    model = PDBParser(QUIET=True).get_structure(path.stem, path)[0]
    residues = [residue for chain in model for residue in chain if "CA" in residue]
    bare = [
        residue.id[1] for residue in residues[binder_length:]
        if residue.resname != "GLY"
        and not any(atom.id not in ("N", "CA", "C", "O") for atom in residue)
    ]
    if bare:
        raise ValueError(f"{path.name}: target residues without sidechains: {bare}")


def run(root, release, upstream, settings):
    reference = root / "inputs/target_1www_chainX.pdb"
    rows = list(csv.DictReader((release / "TrkA_designs.csv").open(encoding="utf-8")))
    sequences = read_sequences(release / "TrkA_binders.fasta")
    selected = select(rows, settings["non_binders"], settings["seed"])

    directory = root / "work"
    (directory / "prepared").mkdir(parents=True)
    records, failures = [], []
    print(f"설계 {len(selected)}개 준비 시작 "
          f"(결합 {sum(r['Binder'] == 'True' for r in selected)}, "
          f"비결합 {sum(r['Binder'] != 'True' for r in selected)})", flush=True)
    for index, row in enumerate(selected, 1):
        record = {
            "design": row["RFdiffusion_output"],
            "af2": row["AF2_prediction"],
            "binder_experimental": row["Binder"] == "True",
            "noise_level": row["Noise_level"],
            "fold_conditioned": row["Fold_conditioned"] == "True",
            "monomeric": row["Monomeric"] == "True",
            "sequence": sequences[row["AF2_prediction"]],
        }
        record["length"] = len(record["sequence"])
        try:
            prepared, target, grafted = prepare(record, release, reference, directory)
            check_sidechains(prepared, record["length"])
            record["prepared"] = prepared.name
            record["target_sequence"] = target
            record["grafted"] = grafted.name
            records.append(record)
            print(f"  {index}/{len(selected)} {record['design']} "
                  f"({'결합' if record['binder_experimental'] else '비결합'}, "
                  f"{record['length']}잔기) 준비됨", flush=True)
        except Exception as error:
            failures.append({**record, "error": str(error)})
            print(f"  {index}/{len(selected)} {record['design']} 준비 실패: {error}", flush=True)
    print(f"준비 완료 {len(records)}개, 실패 {len(failures)}개. "
          f"이제 AF2를 {len(records)}회 실행합니다 (설계당 약 2분).", flush=True)
    (root / "prepare_failures.json").write_text(json.dumps(failures, indent=2))

    sys.argv = [
        str(upstream / "af2_initial_guess/predict.py"),
        "-pdbdir", str(directory / "prepared"),
        "-outpdbdir", str(root / "predictions"),
        "-scorefilename", str(root / "scores.sc"),
        "-checkpoint_name", str(root / "af2.checkpoint"),
        "-recycle", str(settings["recycles"]),
    ]
    runpy.run_path(sys.argv[0], run_name="__main__")

    score_lines = (root / "scores.sc").read_text().splitlines()
    header = next(line.split()[1:] for line in score_lines if line.startswith("SCORE:") and "description" in line)
    scores = {}
    for line in score_lines:
        if not line.startswith("SCORE:") or "description" in line:
            continue
        values = dict(zip(header, line.split()[1:], strict=True))
        scores[values["description"].removesuffix("_af2pred")] = values

    results = []
    for record in records:
        name = record["design"]
        row = {k: v for k, v in record.items() if k != "sequence"}
        score = scores.get(name)
        if score is None:
            results.append({**row, "status": "no_score"})
            continue
        prediction = root / "predictions" / f"{name}_af2pred.pdb"
        canonical = directory / f"{name}_canonical.pdb"
        canonical.write_text(design_reference(release / "rfdiffusion" / f"{name}.pdb", record["sequence"]))
        published = release / "af2" / f"{record['af2']}.pdb"
        row.update({
            "status": "success",
            "pae_interaction": float(score["pae_interaction"]),
            "plddt_binder": float(score["plddt_binder"]),
            "plddt_target": float(score["plddt_target"]),
            "binder_aligned_rmsd": float(score["binder_aligned_rmsd"]),
            "target_aligned_rmsd": float(score["target_aligned_rmsd"]),
            "seconds": float(score["time"]),
            "rmsd_vs_design": pose_rmsd(canonical, prediction, record["target_sequence"], record["sequence"]),
            "rmsd_vs_published_af2": pose_rmsd(published, prediction, record["target_sequence"], record["sequence"]),
        })
        row["passes_filter"] = bool(
            row["pae_interaction"] < PAE_PASS
            and row["plddt_binder"] > PLDDT_PASS
            and row["binder_aligned_rmsd"] < RMSD_PASS
        )
        results.append(row)

    columns = sorted({key for row in results for key in row})
    columns = ["design", "binder_experimental", "passes_filter", "pae_interaction", "plddt_binder",
               "binder_aligned_rmsd", "target_aligned_rmsd", "rmsd_vs_design",
               "rmsd_vs_published_af2", "length"] + [c for c in columns if c not in {
                   "design", "binder_experimental", "passes_filter", "pae_interaction", "plddt_binder",
                   "binder_aligned_rmsd", "target_aligned_rmsd", "rmsd_vs_design",
                   "rmsd_vs_published_af2", "length"}]
    with (root / "calibration.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    (root / "calibration.json").write_text(json.dumps(results, indent=2))

    done = [row for row in results if row.get("status") == "success"]
    groups = {
        "binders": [row for row in done if row["binder_experimental"]],
        "non_binders": [row for row in done if not row["binder_experimental"]],
    }
    summary = {"pass_thresholds": {"pae_interaction": PAE_PASS, "plddt_binder": PLDDT_PASS,
                                   "binder_aligned_rmsd": RMSD_PASS}}
    for name, group in groups.items():
        if not group:
            summary[name] = {"count": 0}
            continue
        pae = np.array([row["pae_interaction"] for row in group])
        summary[name] = {
            "count": len(group),
            "pae_interaction": {"min": float(pae.min()), "median": float(np.median(pae)),
                                "max": float(pae.max()), "mean": float(pae.mean())},
            "passes_filter": sum(row["passes_filter"] for row in group),
        }
    (root / "calibration_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("release", type=Path)
    parser.add_argument("upstream", type=Path)
    arguments = parser.parse_args()
    import pyrosetta

    pyrosetta.init("-mute all -constant_seed -jran 1111111")
    run(arguments.root, arguments.release, arguments.upstream,
        json.loads((arguments.root / "settings.json").read_bytes()))
