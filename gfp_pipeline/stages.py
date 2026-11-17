import csv
import json
import math
import re
import sys
from urllib.request import urlopen

import numpy as np

from common import AA, ROOT, measure, save_cif, write_csv, write_json
from benchmark import measure_pose, pose_failure_reasons, recovery_criteria


TARGET_PDB = "3G9A"
TARGET_CHAIN = "A"
CONTACT_RADIUS = 8.0
MAX_TARGET_RMSD = 3.0
MIN_BENCHMARK_CONTACT_JACCARD = 0.5
MIN_DESIGN_HOTSPOT_FRACTION = 2 / 3
MIN_FLUORESCENCE_GROUPS = 3
BACKBONES = 2
SEQUENCES_PER_BACKBONE = 2
BINDER_LENGTH = 55


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def fetch(url):
    with urlopen(url, timeout=45) as response:
        return response.read().decode("utf-8")


def pdb_sequence(pdb, entity):
    fasta = fetch(f"https://www.rcsb.org/fasta/entry/{pdb}/display")
    for record in fasta.split(">")[1:]:
        header, *sequence = record.splitlines()
        if header.partition("|")[0] == f"{pdb}_{entity}":
            return "".join(sequence)
    raise ValueError(f"No FASTA entry for {pdb} entity {entity}.")


def ca_array(atoms, chain):
    return atoms[(atoms.chain_id == chain) & (atoms.atom_name == "CA") & ~atoms.hetero]


def atom_sequence(atoms, chain):
    return "".join(AA[str(residue)] for residue in ca_array(atoms, chain).res_name)


def points_from_pdb(lines, chain):
    return {int(line[22:26]): [float(line[start:start + 8]) for start in (30, 38, 46)]
            for line in lines if line.startswith("ATOM") and line[21] == chain
            and line[12:16].strip() == "CA" and line[16] in " A"}


def prepare():
    from Bio.Align import PairwiseAligner

    crystal = fetch(f"https://files.rcsb.org/download/{TARGET_PDB}.pdb").splitlines()
    target_points = points_from_pdb(crystal, TARGET_CHAIN)
    control_points = points_from_pdb(crystal, "B")
    positions = np.array(sorted(target_points))
    distances = np.linalg.norm(np.array([target_points[i] for i in positions])[:, None, :]
                               - np.array(list(control_points.values()))[None, :, :], axis=2)
    closest = positions[np.argsort(distances.min(axis=1))[:3]]
    spans = np.split(positions, np.where(np.diff(positions) != 1)[0] + 1)
    contig = ",".join(f"{TARGET_CHAIN}{span[0]}-{span[-1]}" for span in spans)
    target_path = ROOT / "structures/target.pdb"
    target_lines = [line for line in crystal if line.startswith("ATOM")
                    and line[21] == TARGET_CHAIN and line[16] in " A"]
    target_path.write_text("\n".join([*target_lines, "END", ""]))
    write_json(ROOT / "config/rfd3.json", {"gfp": {
        "input": str(target_path), "dialect": 2, "infer_ori_strategy": "hotspots",
        "contig": f"{BINDER_LENGTH}-{BINDER_LENGTH},/0,{contig}",
        "select_hotspots": {f"{TARGET_CHAIN}{index}": "CA" for index in closest},
        "is_non_loopy": True,
    }})

    target_sequence = pdb_sequence(TARGET_PDB, "1")
    if target_sequence.count("X") != 1 or "TTFXVQ" not in target_sequence:
        raise ValueError("Expected one collapsed GFP chromophore at TTFXVQ.")
    chromophore_index = target_sequence.index("X")
    target_sequence = target_sequence.replace("X", "SYG")
    ca_residues = {int(line[22:26]): AA[line[17:20].strip()]
                   for line in target_lines if line[12:16].strip() == "CA"}
    observed = "".join(ca_residues[index] for index in positions)
    aligner = PairwiseAligner(match_score=2, mismatch_score=-3,
                              open_gap_score=-5, extend_gap_score=-0.5)
    alignment = next(iter(aligner.align(target_sequence, observed)))
    mapped_positions = {int(positions[j]): int(i)
                        for i, j in zip(*alignment.indices) if i >= 0 and j >= 0}
    write_json(ROOT / "config/target.json", {
        "sequence": target_sequence, "pdb": TARGET_PDB, "chain": TARGET_CHAIN,
        "chromophore_indices": list(range(chromophore_index, chromophore_index + 3)),
        "hotspots": closest.tolist(),
        "hotspot_indices": [mapped_positions[int(index)] for index in closest],
        "observed_indices": {str(index): mapped_positions[index] for index in target_points},
    })

    with (ROOT / "config/assays.csv").open(encoding="utf-8-sig", newline="") as handle:
        assays = list(csv.DictReader(handle))
    ids = set()
    sequences = set()
    assay_ids = {row["assay"].strip() for row in assays}
    if len(assays) < 2 or len(assay_ids) != 1 or "" in assay_ids:
        raise ValueError("Supply at least two measured controls from one assay.")
    for row in assays:
        ident = row["id"].strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", ident) or ident in ids:
            raise ValueError(f"Invalid or duplicate control ID: {ident!r}")
        ids.add(ident)
        row["id"] = "control_" + ident
        ratio = float(row["ratio"])
        if not math.isfinite(ratio) or ratio <= 0 or not row["group"].strip() or not row["source"].strip():
            raise ValueError(f"Invalid ratio, group or source for control {ident!r}.")
        seq = (row.get("sequence") or "").strip().upper()
        if not seq:
            seq = pdb_sequence(row["pdb"].upper(), row["entity"]).removesuffix("HHHHHH")
        if not seq or set(seq) - set(AA.values()) or seq in sequences:
            raise ValueError(f"Invalid or duplicate control sequence: {ident!r}")
        sequences.add(seq)
        row.update(sequence=seq, ratio=ratio, group=row["group"].strip())
    write_json(ROOT / "config/controls.json", assays)
    benchmarks = []
    source = read_json("config/source.json")
    benchmark_only = source.get("mode") == "benchmark"
    selected_controls = source.get("benchmark_controls", ["enhancer", "minimizer"])
    for name, pdb, binder_chain in (("enhancer", "3K1K", "C"), ("minimizer", TARGET_PDB, "B")):
        if benchmark_only and name not in selected_controls:
            continue
        lines = crystal if pdb == TARGET_PDB else fetch(f"https://files.rcsb.org/download/{pdb}.pdb").splitlines()
        gfp = points_from_pdb(lines, TARGET_CHAIN)
        binder = np.array(list(points_from_pdb(lines, binder_chain).values()))
        comparable = sorted(gfp.keys() & mapped_positions.keys())
        contacts = np.linalg.norm(np.array([gfp[index] for index in comparable])[:, None, :]
                                  - binder[None, :, :], axis=2)
        sequence = pdb_sequence(pdb, "2").removesuffix("HHHHHH")
        shared = next((row["id"] for row in assays if row["sequence"] == sequence), None)
        benchmark = {
            "id": shared or f"benchmark_{name}", "name": name, "pdb": pdb, "sequence": sequence,
            "reference_indices": [mapped_positions[index] for index in comparable],
            "contact_indices": [mapped_positions[index] for index, hit in
                                zip(comparable, (contacts <= CONTACT_RADIUS).any(axis=1), strict=True)
                                if hit],
        }
        from benchmark import make_reference

        reference_sequence = pdb_sequence(pdb, "1")
        if reference_sequence.count("X") != 1 or "TTFXVQ" not in reference_sequence:
            raise ValueError(f"Unexpected GFP chromophore sequence in {pdb}.")
        reference = make_reference(lines, TARGET_CHAIN, binder_chain,
                                   reference_sequence.replace("X", "SYG"), sequence)
        reference_path = f"config/reference_{name}.json"
        write_json(ROOT / reference_path, reference)
        benchmark["reference_file"] = reference_path
        benchmarks.append(benchmark)
    write_json(ROOT / "config/benchmarks.json", benchmarks)


def generate_backbones():
    from rfd3.engine import RFD3InferenceConfig, RFD3InferenceEngine

    with measure("RFD3", "generation", "gfp"):
        config = RFD3InferenceConfig(
            diffusion_batch_size=1, low_memory_mode=False, compile_model=False,
            compile_cuda_graphs=False, inference_kernel_backend="torch", seed=0,
            inference_sampler={"num_timesteps": 200, "step_scale": 3.0, "gamma_0": 0.2},
        )
        model = RFD3InferenceEngine(**config)
        model._assign_override("trainer.precision", "32-true")
        output = model.run(inputs=str(ROOT / "config/rfd3.json"), n_batches=BACKBONES)
    samples = [sample for batch in (output or {}).values() for sample in batch]
    if len(samples) != BACKBONES:
        raise RuntimeError(f"Expected {BACKBONES} RFD3 structures, got {len(samples)}.")
    rows = []
    for index, sample in enumerate(samples, 1):
        atoms = sample.atom_array
        chains = np.unique(atoms.chain_id)
        binders = [str(chain) for chain in chains if len(ca_array(atoms, chain)) == BINDER_LENGTH]
        if len(binders) != 1:
            raise RuntimeError(f"Could not identify the designed chain in sample {index}.")
        ident = f"backbone_{index:02d}"
        path = f"structures/{ident}.cif"
        save_cif(atoms, ROOT / path)
        rows.append({"id": ident, "file": path, "binder_chain": binders[0]})
    write_json(ROOT / "config/backbones.json", rows)


def design_sequences():
    from mpnn.inference_engines.mpnn import MPNNInferenceEngine

    model = MPNNInferenceEngine(model_type="ligand_mpnn", is_legacy_weights=True,
                               write_structures=False, write_fasta=False, device="cuda")
    designs = []
    for backbone in read_json("config/backbones.json"):
        ident = backbone["id"]
        chain = backbone["binder_chain"]
        with measure("LigandMPNN", "design", ident):
            results = model.run(input_dicts=[{
                "structure_path": str(ROOT / backbone["file"]), "name": ident,
                "designed_chains": [chain], "batch_size": SEQUENCES_PER_BACKBONE,
                "temperature": 0.1, "seed": 0, "remove_waters": True,
            }])
        for index, result in enumerate(results, 1):
            seq = atom_sequence(result.atom_array, chain)
            if len(seq) != BINDER_LENGTH:
                raise RuntimeError(f"Unexpected binder length for {ident}.")
            designs.append({"id": f"{ident}_seq{index:02d}", "sequence": seq,
                            "backbone": backbone["file"]})
    write_json(ROOT / "config/designs.json", designs)
    (ROOT / "structures/designs.fasta").write_text("".join(
        f">{row['id']}\n{row['sequence']}\n" for row in designs))


def interface_features(atoms, target):
    target_ca = ca_array(atoms, "A")
    binder_ca = ca_array(atoms, "B")
    if not len(target_ca) or not len(binder_ca):
        raise ValueError("Expected two complex chains with C-alpha coordinates.")
    if atom_sequence(atoms, "A") != target["sequence"]:
        raise ValueError("RF3 GFP chain does not match the target sequence.")
    if not (np.isfinite(target_ca.coord).all() and np.isfinite(binder_ca.coord).all()):
        raise ValueError("RF3 complex has unresolved C-alpha coordinates.")
    distances = np.linalg.norm(target_ca.coord[:, None] - binder_ca.coord[None, :], axis=2)
    contacts = distances <= CONTACT_RADIUS
    return {
        "hotspot_contact_fraction": float(np.mean(contacts[target["hotspot_indices"]].any(axis=1))),
        "target_contact_fraction": float(np.mean(contacts.any(axis=1))),
        "binder_contact_fraction": float(np.mean(contacts.any(axis=0))),
        "chromophore_ca_distance": float(distances[target["chromophore_indices"]].min()),
        "target_contact_indices": np.flatnonzero(contacts.any(axis=1)).tolist(),
    }


def read_target_template(target):
    mapping = target["observed_indices"]
    lines = (ROOT / "structures/target.pdb").read_text().splitlines()
    coords = {(mapping[line[22:26].strip()], line[12:16].strip()):
              [float(line[start:start + 8]) for start in (30, 38, 46)]
              for line in lines if line.startswith("ATOM") and line[22:26].strip() in mapping}
    return coords


def apply_target_template(atoms, target_sequence, template):
    if atom_sequence(atoms, "A") != target_sequence:
        raise ValueError("RF3 input GFP chain does not match the full target sequence.")
    positions = {int(res_id): index for index, res_id in enumerate(ca_array(atoms, "A").res_id)}
    selected = np.zeros(len(atoms), dtype=bool)
    for i in np.flatnonzero(atoms.chain_id == "A"):
        key = (positions[int(atoms.res_id[i])], str(atoms.atom_name[i]))
        if key in template:
            atoms.coord[i] = template[key]
            selected[i] = True
    if np.count_nonzero(selected & (atoms.atom_name == "CA")) != sum(
        atom == "CA" for _, atom in template
    ):
        raise ValueError("RF3 template lost observed GFP C-alpha positions.")
    # RF3 builds its template distances from observed, occupied atoms.
    atoms.occupancy[selected] = 1.0
    atoms.set_annotation("is_input_file_templated", selected)


def target_rmsd(atoms, template):
    reference_by_index = {index: coord for (index, atom), coord in template.items() if atom == "CA"}
    indices = sorted(reference_by_index)
    reference = np.array([reference_by_index[index] for index in indices])
    mobile = ca_array(atoms, "A").coord[indices].astype(np.float64)
    if not np.isfinite(mobile).all():
        raise ValueError("RF3 GFP chain contains unresolved coordinates.")
    mobile = mobile - mobile.mean(axis=0)
    reference -= reference.mean(axis=0)
    u, _, vt = np.linalg.svd(mobile.T @ reference)
    rotation = u @ np.diag([1, 1, np.linalg.det(u @ vt)]) @ vt
    return float(np.sqrt(np.mean(np.sum((mobile @ rotation - reference) ** 2, axis=1))))


def predict_complexes(benchmark_seed=None):
    from rf3.utils.inference import InferenceInput
    from rf3_runtime import create_model

    seed = 0 if benchmark_seed is None else benchmark_seed
    source = read_json("config/source.json")
    settings = source.get("rf3", {"num_steps": 50, "n_recycles": 3, "diffusion_batch_size": 1})
    template_mode = source["benchmark_template"] if benchmark_seed is not None else None
    model = create_model(settings, seed, template_mode)
    if benchmark_seed is not None:
        from benchmark import apply_chain_templates, measure_pose

    target = read_json("config/target.json")
    template = read_target_template(target)
    benchmarks = read_json("config/benchmarks.json")
    benchmark_by_id = {row["id"]: row for row in benchmarks}
    inputs = {row["id"]: row for row in benchmarks}
    if benchmark_seed is None:
        for row in read_json("config/designs.json") + read_json("config/controls.json"):
            inputs.setdefault(row["id"], row)
    suffix = "" if benchmark_seed is None else f"_seed{seed}"
    rows = []
    for item in inputs.values():
        ident = item["id"]
        reference = read_json(item["reference_file"]) if benchmark_seed is not None else None
        target_sequence = reference["target"]["sequence"] if reference else target["sequence"]
        payload = {"name": ident, "components": [
            {"chain_id": "A", "seq": target_sequence},
            {"chain_id": "B", "seq": item["sequence"]},
        ]}
        with measure("RF3", "complex", ident):
            input_spec = InferenceInput.from_json_dict(payload)
            if reference:
                apply_chain_templates(input_spec.atom_array, reference, template_mode, seed)
            else:
                apply_target_template(input_spec.atom_array, target["sequence"], template)
            predictions = model.run(inputs=input_spec, out_dir=None)
        prediction, = predictions[ident]
        if atom_sequence(prediction.atom_array, "B") != item["sequence"]:
            raise ValueError(f"RF3 binder chain does not match {ident}.")
        path = f"structures/{ident}{suffix}.cif"
        save_cif(prediction.atom_array, ROOT / path)
        summary = prediction.summary_confidences
        if reference:
            if atom_sequence(prediction.atom_array, "A") != target_sequence:
                raise ValueError(f"RF3 GFP chain does not match reference for {ident}.")
            rows.append({
                "id": ident, "file": path, "reference_pdb": item["pdb"],
                "template_mode": template_mode, **settings,
                "iptm": summary.get("iptm"), "ranking_score": summary.get("ranking_score"),
                "has_clash": bool(summary.get("has_clash", False)),
                **measure_pose(ca_array(prediction.atom_array, "A").coord,
                               ca_array(prediction.atom_array, "B").coord,
                               reference, CONTACT_RADIUS),
            })
            write_csv(ROOT / f"metrics/complexes{suffix}.csv", rows)
            continue
        features = interface_features(prediction.atom_array, target)
        contacts = set(features.pop("target_contact_indices"))
        rmsd = target_rmsd(prediction.atom_array, template)
        pose_metrics = {}
        if benchmark := benchmark_by_id.get(ident):
            from Bio.Align import PairwiseAligner
            native = read_json(benchmark["reference_file"])
            aligner = PairwiseAligner(match_score=2, mismatch_score=-3, open_gap_score=-5, extend_gap_score=-0.5)
            mapping = next(iter(aligner.align(native["target"]["sequence"], target_sequence)))
            native_target = np.full((len(native["target"]["sequence"]), 3), np.nan)
            current_target = ca_array(prediction.atom_array, "A").coord
            for native_index, current_index in zip(*mapping.indices):
                if native_index >= 0 and current_index >= 0:
                    native_target[native_index] = current_target[current_index]
            pose_metrics = measure_pose(native_target, ca_array(prediction.atom_array, "B").coord,
                                        native, CONTACT_RADIUS)
        rows.append({
            "id": ident, "file": path, "iptm": summary.get("iptm"),
            "ranking_score": summary.get("ranking_score"),
            "has_clash": bool(summary.get("has_clash", False)),
            "target_ca_rmsd_angstrom": rmsd, "benchmark_contact_jaccard": None,
            **features, **pose_metrics,
        })
        write_csv(ROOT / f"metrics/complexes{suffix}.csv", rows)
    write_json(ROOT / f"metrics/complexes{suffix}.json", rows)


def benchmark_pose_passed(row):
    return not pose_failure_reasons(row)


def summarize_benchmark():
    source = read_json("config/source.json")
    seeds = source["rf3_seeds"]
    benchmarks = read_json("config/benchmarks.json")
    expected = {row["id"] for row in benchmarks}
    predictions = {ident: [] for ident in expected}
    for seed in seeds:
        rows = read_json(f"metrics/complexes_seed{seed}.json")
        if len(rows) != len(expected) or {row["id"] for row in rows} != expected:
            raise ValueError(f"Unexpected structural controls in RF3 output for seed {seed}.")
        for row in rows:
            if row["iptm"] is None or not math.isfinite(row["iptm"]):
                raise ValueError(f"Missing finite ipTM for {row['id']} at seed {seed}.")
            predictions[row["id"]].append({"seed": seed, **row})

    summary = []
    poses = []
    for control in benchmarks:
        ranked = sorted(predictions[control["id"]], key=lambda row: (-row["iptm"], row["seed"]))
        top = ranked[0]
        passing_ranks = []
        for rank, row in enumerate(ranked, 1):
            row["pose_failure_reasons"] = pose_failure_reasons(row)
            passed = not row["pose_failure_reasons"]
            poses.append({"iptm_rank": rank, "reference_pose_recovered": passed, **row})
            if passed:
                passing_ranks.append(rank)
        if not passing_ranks:
            status = "no_pose_recovered"
        elif passing_ranks[0] == 1:
            status = "top_pose_recovered"
        else:
            status = "pose_ranked_lower"
        best_contact = max(ranked, key=lambda row: row["benchmark_contact_jaccard"])
        summary.append({
            "control": control["name"], "reference_pdb": control["pdb"],
            "status": status, "poses_tested": len(ranked), "poses_recovered": len(passing_ranks),
            "top_iptm_seed": top["seed"], "top_iptm": top["iptm"],
            "top_iptm_contact_jaccard": top["benchmark_contact_jaccard"],
            "best_contact_seed": best_contact["seed"],
            "best_contact_jaccard": best_contact["benchmark_contact_jaccard"],
            "top_iptm_binder_rmsd_angstrom": top.get("binder_ca_rmsd_after_target_alignment_angstrom"),
            "top_iptm_native_ca_contact_pair_recovery": top.get("native_ca_contact_pair_recovery"),
            "best_binder_rmsd_angstrom": min(
                (row["binder_ca_rmsd_after_target_alignment_angstrom"] for row in ranked
                 if "binder_ca_rmsd_after_target_alignment_angstrom" in row), default=None),
            "best_native_ca_contact_pair_recovery": max(
                (row["native_ca_contact_pair_recovery"] for row in ranked
                 if "native_ca_contact_pair_recovery" in row), default=None),
            "best_recovered_iptm_rank": passing_ranks[0] if passing_ranks else None,
        })
    write_csv(ROOT / "metrics/benchmark_poses.csv", poses)
    write_csv(ROOT / "metrics/benchmark_summary.csv", summary)
    write_json(ROOT / "metrics/benchmark_summary.json", {
        "seeds": seeds, "max_target_ca_rmsd_angstrom": MAX_TARGET_RMSD,
        "template_mode": source.get("benchmark_template"), "rf3": source.get("rf3"),
        "contact_radius_angstrom": CONTACT_RADIUS,
        "recovery_criterion": "target_and_binder_structure_contacts_without_clash",
        "recovery_criteria": recovery_criteria(),
        "min_contact_jaccard": MIN_BENCHMARK_CONTACT_JACCARD, "controls": summary,
    })


def predict_fluorescence():
    from sklearn.linear_model import Ridge
    from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    features = ("target_contact_fraction", "binder_contact_fraction", "chromophore_ca_distance")
    complexes = {row["id"]: row for row in read_json("metrics/complexes.json")}
    controls = read_json("config/controls.json")
    designs = read_json("config/designs.json")
    benchmarks = read_json("config/benchmarks.json")
    benchmark_passed = all(benchmark_pose_passed(complexes[row["id"]]) for row in benchmarks)
    valid_controls = [row for row in controls
                      if complexes[row["id"]]["target_ca_rmsd_angstrom"] <= MAX_TARGET_RMSD
                      and not complexes[row["id"]]["has_clash"]]
    groups = [row["group"] for row in valid_controls]
    model = make_pipeline(StandardScaler(), Ridge(alpha=1.0))
    report = {
        "n_controls": len(controls), "n_valid_controls": len(valid_controls),
        "n_groups": len(set(groups)), "benchmarks_passed": benchmark_passed,
        "recovery_criteria": recovery_criteria(),
        "assay": controls[0]["assay"], "feature_names": features,
        "max_target_ca_rmsd_angstrom": MAX_TARGET_RMSD,
        "min_benchmark_contact_jaccard": MIN_BENCHMARK_CONTACT_JACCARD,
        "min_candidate_hotspot_fraction": MIN_DESIGN_HOTSPOT_FRACTION,
        "min_fluorescence_groups": MIN_FLUORESCENCE_GROUPS,
        "label": "log2(GFP with binder fluorescence / reference fluorescence)",
        "scope": "In-range estimates from experimentally measured controls.",
    }
    status = "insufficient_control_groups"
    if not benchmark_passed:
        status = "structural_benchmark_failed"
    elif len(set(groups)) >= MIN_FLUORESCENCE_GROUPS:
        train = np.array([[complexes[row["id"]][key] for key in features] for row in valid_controls])
        target = np.log2([row["ratio"] for row in valid_controls])
        held_out = cross_val_predict(model, train, target, groups=groups, cv=LeaveOneGroupOut())
        report["held_out_mae_log2"] = float(np.mean(np.abs(held_out - target)))
        report["no_effect_mae_log2"] = float(np.mean(np.abs(target)))
        status = "baseline_not_improved"
        if report["held_out_mae_log2"] < report["no_effect_mae_log2"]:
            model.fit(train, target)
            lower, upper = train.min(axis=0), train.max(axis=0)
            minimum_score, maximum_score = target.min(), target.max()
            report["training_feature_range"] = {
                key: [low, high] for key, low, high in zip(features, lower, upper, strict=True)
            }
            report["training_log2_effect_range"] = [minimum_score, maximum_score]
            status = "ready"
    report["validation"] = status
    results = []
    for design in designs:
        result = complexes[design["id"]]
        reason = status
        score = None
        if (result["has_clash"] or result["target_ca_rmsd_angstrom"] > MAX_TARGET_RMSD
                or result["hotspot_contact_fraction"] < MIN_DESIGN_HOTSPOT_FRACTION):
            reason = "candidate_structure_failed"
        elif status == "ready":
            vector = np.array([result[key] for key in features])
            reason = "outside_training_range"
            if np.all((lower <= vector) & (vector <= upper)):
                estimate = float(model.predict(vector[None, :])[0])
                reason = "outside_observed_effect_range"
                if minimum_score <= estimate <= maximum_score:
                    score = estimate
                    reason = "predicted"
        results.append({
            "id": design["id"], "sequence": design["sequence"], "complex": result["file"],
            "iptm": result["iptm"], "prediction_status": reason,
            "predicted_log2_ratio": score,
            "predicted_fluorescence_ratio": None if score is None else float(2 ** score),
        })
    write_json(ROOT / "metrics/fluorescence_model.json", report)
    write_csv(ROOT / "metrics/fluorescence_predictions.csv", results)


if __name__ == "__main__":
    handlers = {"prepare": prepare, "backbones": generate_backbones, "sequences": design_sequences,
                "complexes": predict_complexes, "fluorescence": predict_fluorescence,
                "benchmark": predict_complexes, "benchmark_report": summarize_benchmark}
    handlers[sys.argv[1]](*map(int, sys.argv[2:]))
