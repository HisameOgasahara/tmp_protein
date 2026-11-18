import argparse
import ast
import hashlib
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from compare import design_reference, pose_rmsd, read_inputs
from target_sidechains import design_with_target_sidechains


def save_arrays(path, values):
    numeric = {}
    metadata = {}
    for key, value in values.items():
        array = np.asarray(value)
        metadata[key] = {"shape": list(array.shape), "dtype": str(array.dtype)}
        if array.dtype.kind not in "biufc":
            continue
        numeric[key] = array
        metadata[key]["sha256"] = hashlib.sha256(array.tobytes()).hexdigest()
    np.savez_compressed(path, **numeric)
    path.with_suffix(".json").write_text(json.dumps(metadata, indent=2))


def original_thread(pose, sequence, upstream):
    import pyrosetta

    path = upstream / "mpnn_fr/dl_interface_design.py"
    tree = ast.parse(path.read_bytes())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "sample_features")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "thread_mpnn_seq")
    mapping = dict(zip(
        "ARNDCQEGHILKMFPSTWYV-",
        ("ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY", "HIS", "ILE",
         "LEU", "LYS", "MET", "PHE", "PRO", "SER", "THR", "TRP", "TYR", "VAL", "GAP"),
        strict=True,
    ))
    namespace = {"core": pyrosetta.rosetta.core, "mpnn_util": SimpleNamespace(aa_1_3=mapping)}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), namespace)
    namespace["thread_mpnn_seq"](SimpleNamespace(pose=pose), sequence)


def prepare_input(inputs, directory, case, upstream):
    import pyrosetta
    from pyrosetta.toolbox.mutants import mutate_residue

    target, binder = read_inputs(inputs)
    pyrosetta.init("-mute all -constant_seed -jran 1111111")
    if case["input"] == "published":
        pose = pyrosetta.pose_from_pdb(str(inputs / "published_af2.pdb"))
    else:
        source = inputs / "design.pdb"
        if case["input"] == "grafted_target":
            source = directory / "design_with_target_sidechains.pdb"
            source.write_text(design_with_target_sidechains(inputs))
        pose = pyrosetta.pose_from_pdb(str(source))
        if case["threading"] == "mutate":
            for index, residue in enumerate(binder, 1):
                mutate_residue(pose, index, residue)
        else:
            original_thread(pose, binder, upstream)
        if case["input"] == "published_target":
            from Bio.PDB import PDBParser, Superimposer

            parser = PDBParser(QUIET=True)
            design = parser.get_structure("design", inputs / "design.pdb")[0]["B"]
            published = parser.get_structure("published", inputs / "published_af2.pdb")[0]["B"]
            alignment = Superimposer()
            alignment.set_atoms([r["CA"] for r in design], [r["CA"] for r in published])
            rotation, translation = alignment.rotran
            for offset, residue in enumerate(published, len(binder) + 1):
                for atom in residue:
                    if pose.residue(offset).has(atom.id):
                        point = atom.coord @ rotation + translation
                        pose.set_xyz(
                            pyrosetta.rosetta.core.id.AtomID(pose.residue(offset).atom_index(atom.id), offset),
                            pyrosetta.rosetta.numeric.xyzVector_double_t(*map(float, point)),
                        )
    if pose.sequence() != binder + target or pose.chain_end(1) != len(binder):
        raise ValueError("Prepared candidate sequence or chain order is incorrect.")
    path = directory / "prepared/TrkA_88.pdb"
    path.parent.mkdir()
    pose.dump_pdb(str(path))
    return target, binder, path


def observe_model(directory, case):
    import jax
    from alphafold.model import model

    original_class = model.RunModel

    def create_runner(config, params=None):
        (directory / "model_config.json").write_text(config.to_json())
        runner = original_class(config, params)
        process = runner.process_features
        apply = runner.apply

        def process_features(raw, random_seed=0):
            raw = dict(raw)
            if not case["target_template"]:
                raw["template_all_atom_masks"] = np.zeros_like(raw["template_all_atom_masks"])
                raw["template_all_atom_positions"] = np.zeros_like(raw["template_all_atom_positions"])
            save_arrays(directory / "raw_features.npz", raw)
            features = process(raw, random_seed=case["seed"])
            save_arrays(directory / "processed_features.npz", features)
            return features

        def apply_model(parameters, key, features, initial_guess=None):
            save_arrays(directory / "initial_guess.npz", {"coordinates": initial_guess})
            result = apply(parameters, jax.random.PRNGKey(case["seed"]), features, initial_guess)
            metrics = model.get_confidence_metrics(result)
            save_arrays(directory / "confidence.npz", metrics)
            return result

        runner.process_features = process_features
        runner.apply = apply_model
        return runner

    model.RunModel = create_runner


def run_case(directory, inputs, upstream, case):
    import jax

    if case["precision"] == "highest":
        jax.config.update("jax_default_matmul_precision", "highest")
    (directory / "runtime_settings.json").write_text(json.dumps({
        "jax_version": jax.__version__,
        "devices": [str(device) for device in jax.devices()],
        "matmul_precision": jax.config.jax_default_matmul_precision,
        "rosetta_seed": 1111111,
    }, indent=2))
    target, binder, prepared = prepare_input(inputs, directory, case, upstream)
    canonical = directory / "canonical_design.pdb"
    canonical.write_text(design_reference(inputs, binder))
    observe_model(directory, case)
    script = upstream / "af2_initial_guess/predict.py"
    command = [
        str(script), "-pdbdir", str(prepared.parent),
        "-outpdbdir", str(directory / "output"),
        "-scorefilename", str(directory / "scores.sc"),
        "-checkpoint_name", str(directory / "af2.checkpoint"),
        "-recycle", str(case["recycles"]), "-debug",
    ]
    if not case["initial_guess"]:
        command.append("-no_initial_guess")
    sys.argv = command
    runpy.run_path(str(script), run_name="__main__")
    prediction = directory / "output/TrkA_88_af2pred.pdb"
    score_lines = (directory / "scores.sc").read_text().splitlines()
    header, values = [line.split()[1:] for line in score_lines if line.startswith("SCORE:")]
    scores = dict(zip(header, values, strict=True))
    report = {
        **case, "status": "success",
        "rmsd_vs_original_design": pose_rmsd(canonical, prediction, target, binder),
        "rmsd_vs_published_af2": pose_rmsd(inputs / "published_af2.pdb", prediction, target, binder),
        "input_rmsd_vs_design": pose_rmsd(canonical, prepared, target, binder),
        "plddt_binder": float(scores["plddt_binder"]),
        "pae_interaction": float(scores["pae_interaction"]),
        "binder_aligned_rmsd": float(scores["binder_aligned_rmsd"]),
        "original_scores": scores,
    }
    (directory / "result.json").write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("inputs", type=Path)
    parser.add_argument("upstream", type=Path)
    arguments = parser.parse_args()
    run_case(arguments.directory, arguments.inputs, arguments.upstream,
             json.loads((arguments.directory / "case.json").read_bytes()))
