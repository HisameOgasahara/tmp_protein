"""Score newly designed binders with the same filter used on the published set.

Takes a manifest of {name, design_pdb, sequence} produced by the design stage,
prepares every complex the same way the published designs were prepared, and
hands them all to the upstream predictor in one call.

The published binder TrkA_88 is scored alongside as a positive control, so every
result table carries a row whose experimental outcome is known.
"""

import argparse
import csv
import json
import runpy
import sys
from pathlib import Path

from calibration import PAE_PASS, PLDDT_PASS, RMSD_PASS, check_sidechains
from compare import design_reference, pose_rmsd
from target_sidechains import complex_with_target_sidechains


def prepare_one(name, design_path, sequence, reference, directory):
    """Graft the target sidechains, thread the sequence, dump an AF2 input."""
    import pyrosetta
    from pyrosetta.toolbox.mutants import mutate_residue

    grafted = directory / f"{name}_grafted.pdb"
    grafted.write_text(complex_with_target_sidechains(design_path, reference))
    pose = pyrosetta.pose_from_pdb(str(grafted))
    if pose.chain_end(1) != len(sequence):
        raise ValueError(f"{name}: chain 1 has {pose.chain_end(1)} residues, "
                         f"sequence has {len(sequence)}.")
    for index, residue in enumerate(sequence, 1):
        mutate_residue(pose, index, residue)
    target = pose.chain_sequence(2)
    if pose.sequence() != sequence + target:
        raise ValueError(f"{name}: prepared sequence does not match.")
    out = directory / "prepared" / f"{name}.pdb"
    pose.dump_pdb(str(out))
    check_sidechains(out, len(sequence))
    return out, target


def run(root, upstream, settings):
    inputs = root / "inputs"
    reference = inputs / "target_1www_chainX.pdb"
    entries = json.loads((root / "manifest.json").read_bytes())
    # The published binder goes in as a positive control with a known outcome.
    control = "".join((inputs / "binder.fasta").read_text().splitlines()[1:])
    entries = entries + [{"name": "control_TrkA_88", "design_pdb": "inputs/design.pdb",
                          "sequence": control, "control": True}]

    directory = root / "work"
    (directory / "prepared").mkdir(parents=True)
    prepared, failures = [], []
    print(f"복합체 {len(entries)}개 준비 (양성 대조군 1개 포함)", flush=True)
    for index, entry in enumerate(entries, 1):
        name = entry["name"]
        try:
            path, target = prepare_one(name, root / entry["design_pdb"], entry["sequence"],
                                       reference, directory)
            prepared.append({**entry, "target_sequence": target, "prepared": path.name})
            print(f"  {index}/{len(entries)} {name} ({len(entry['sequence'])}잔기) 준비됨", flush=True)
        except Exception as error:
            failures.append({"name": name, "error": str(error)})
            print(f"  {index}/{len(entries)} {name} 준비 실패: {error}", flush=True)
    (root / "prepare_failures.json").write_text(json.dumps(failures, indent=2))
    if not prepared:
        raise RuntimeError("No complex could be prepared.")

    sys.argv = [
        str(upstream / "af2_initial_guess/predict.py"),
        "-pdbdir", str(directory / "prepared"),
        "-outpdbdir", str(root / "predictions"),
        "-scorefilename", str(root / "scores.sc"),
        "-checkpoint_name", str(root / "af2.checkpoint"),
        "-recycle", str(settings["recycles"]),
    ]
    print(f"AF2 {len(prepared)}회 실행", flush=True)
    runpy.run_path(sys.argv[0], run_name="__main__")

    lines = (root / "scores.sc").read_text().splitlines()
    header = next(l.split()[1:] for l in lines if l.startswith("SCORE:") and "description" in l)
    scores = {}
    for line in lines:
        if not line.startswith("SCORE:") or "description" in line:
            continue
        values = dict(zip(header, line.split()[1:], strict=True))
        scores[values["description"].removesuffix("_af2pred")] = values

    results = []
    for entry in prepared:
        name = entry["name"]
        row = {"name": name, "control": bool(entry.get("control")),
               "length": len(entry["sequence"]), "sequence": entry["sequence"]}
        score = scores.get(name)
        if score is None:
            results.append({**row, "status": "no_score"})
            continue
        canonical = directory / f"{name}_canonical.pdb"
        canonical.write_text(design_reference(root / entry["design_pdb"], entry["sequence"]))
        row.update({
            "status": "success",
            "pae_interaction": float(score["pae_interaction"]),
            "plddt_binder": float(score["plddt_binder"]),
            "binder_aligned_rmsd": float(score["binder_aligned_rmsd"]),
            "target_aligned_rmsd": float(score["target_aligned_rmsd"]),
            "seconds": float(score["time"]),
            "rmsd_vs_design": pose_rmsd(canonical, root / "predictions" / f"{name}_af2pred.pdb",
                                        entry["target_sequence"], entry["sequence"]),
        })
        row["passes_filter"] = bool(row["pae_interaction"] < PAE_PASS
                                    and row["plddt_binder"] > PLDDT_PASS
                                    and row["binder_aligned_rmsd"] < RMSD_PASS)
        results.append(row)

    columns = ["name", "control", "passes_filter", "pae_interaction", "plddt_binder",
               "binder_aligned_rmsd", "target_aligned_rmsd", "rmsd_vs_design",
               "length", "status", "seconds", "sequence"]
    with (root / "designs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    (root / "designs.json").write_text(json.dumps(results, indent=2))

    done = [r for r in results if r.get("status") == "success" and not r["control"]]
    passed = [r for r in done if r["passes_filter"]]
    summary = {
        "pass_thresholds": {"pae_interaction": PAE_PASS, "plddt_binder": PLDDT_PASS,
                            "binder_aligned_rmsd": RMSD_PASS},
        "designs_scored": len(done),
        "designs_passing": len(passed),
        "passing_names": [r["name"] for r in passed],
        "control": next(({"name": r["name"], "pae_interaction": r["pae_interaction"],
                          "passes_filter": r["passes_filter"]}
                         for r in results if r["control"] and r.get("status") == "success"), None),
    }
    if done:
        values = sorted(r["pae_interaction"] for r in done)
        summary["pae_interaction"] = {"min": values[0], "median": values[len(values) // 2],
                                      "max": values[-1]}
    (root / "designs_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("upstream", type=Path)
    arguments = parser.parse_args()
    import pyrosetta

    pyrosetta.init("-mute all -constant_seed -jran 1111111")
    run(arguments.root, arguments.upstream,
        json.loads((arguments.root / "settings.json").read_bytes()))
