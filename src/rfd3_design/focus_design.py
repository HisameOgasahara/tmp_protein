"""Resample sequences on one existing backbone, to separate two failure modes.

The 160-design run left one backbone, design_04 of 2026-11-19-trka-design-v2,
placed on the target at 1.190 A -- closer than the published binder TrkA_88
reaches (1.497 A) -- while AF2 still scored its interface at pae_interaction
12.934, outside the pass line of 10. Seven of its eight sequences folded and
placed correctly and none crossed.

That leaves two readings, and they point opposite ways:

  the backbone is the limit   -> no sequence on this shape will cross, and the
                                 budget belongs in generating more shapes
  the sequence search is      -> a crossing sequence exists and eight draws
  the limit                      were too few, so the budget belongs in
                                 sampling more sequences per shape

Fifty fresh sequences on the same backbone separate them. Backbone generation
is skipped entirely, so the run is short, and only two sequence lengths reach
AF2 -- 73 here plus 93 for the control -- so JAX compiles twice.

MPNN's own per-sequence numbers are recorded here for the first time. The
engine's result objects are read for whatever scalars they carry rather than
for an assumed field name, because a wrong guess would silently record nothing.
"""

import json
import shutil
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
# focus_workflow loads this module by path, which does not put its directory on
# sys.path, so the sibling import below would fail without this line.
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from trka_design import read_json, write_json, sequence_of  # noqa: E402

REPOSITORY = SOURCE.parents[1]
SOURCE_RUN = "results/2026-11-19-trka-design-v2"
BACKBONE = "design_04"
BINDER_LENGTH = 73
SEQUENCES = 50
BATCH = 10
SEEDS = (1, 2, 3, 4, 5)   # v0.2.0 drew its eight with seed 0; these are fresh draws.


def prepare_backbone(root):
    """Copy in the chosen backbone and the target it was designed against."""
    sys.path.insert(0, str(SOURCE.parent / "af2_filter"))
    from target_sidechains import graft

    inputs = root / "inputs"
    target = root / "trka_target.pdb"
    target.write_text(graft(inputs / "design.pdb", "B",
                            inputs / "target_1www_chainX.pdb", "X") + "END\n")

    origin = REPOSITORY / SOURCE_RUN / "backbones" / f"{BACKBONE}.pdb"
    if not origin.is_file():
        raise FileNotFoundError(f"Backbone not found in the repository: {origin}")
    destination = root / "backbones" / f"{BACKBONE}.pdb"
    shutil.copyfile(origin, destination)

    length = len({line[22:26] for line in destination.read_text().splitlines()
                  if line.startswith("ATOM") and line[21] == "A"})
    if length != BINDER_LENGTH:
        raise RuntimeError(f"{BACKBONE}: binder has {length} residues, expected "
                           f"{BINDER_LENGTH}. Scoring time and the comparison with "
                           f"the earlier run both assume the stated length.")
    write_json(root / "backbones.json", [{
        "id": BACKBONE, "file": f"backbones/{BACKBONE}.pdb", "binder_length": length,
        "origin": f"{SOURCE_RUN}/backbones/{BACKBONE}.pdb",
    }])
    print(f"백본 {BACKBONE} 복사 완료, 결합여 {length}잔기", flush=True)
    print(f"출처: {SOURCE_RUN}", flush=True)


def scalars(result):
    """Every scalar the engine hangs on a result, by inspection rather than by name."""
    found = {}
    for name in dir(result):
        if name.startswith("_"):
            continue
        try:
            value = getattr(result, name)
        except Exception:
            continue
        if isinstance(value, bool) or callable(value):
            continue
        if isinstance(value, (int, float)):
            found[name] = float(value)
        elif getattr(value, "ndim", None) == 0 or getattr(value, "size", None) == 1:
            try:
                found[name] = float(value.item() if hasattr(value, "item") else value)
            except Exception:
                pass
    return found


def design_sequences(root):
    from mpnn.inference_engines.mpnn import MPNNInferenceEngine

    backbone, = read_json(root / "backbones.json")
    model = MPNNInferenceEngine(model_type="ligand_mpnn", is_legacy_weights=True,
                                write_structures=False, write_fasta=False, device="cuda")
    designs, reported = [], None
    for seed in SEEDS:
        results = model.run(input_dicts=[{
            "structure_path": str(root / backbone["file"]), "name": backbone["id"],
            "designed_chains": ["A"], "batch_size": BATCH,
            "temperature": 0.1, "seed": seed, "remove_waters": True,
        }])
        for result in results:
            sequence = sequence_of(result.atom_array, "A")
            if len(sequence) != backbone["binder_length"]:
                raise RuntimeError(f"MPNN returned {len(sequence)} residues, backbone has "
                                   f"{backbone['binder_length']}.")
            index = len(designs) + 1
            entry = {"name": f"{BACKBONE}_r{index:02d}", "design_pdb": backbone["file"],
                     "sequence": sequence, "mpnn_seed": seed}
            values = scalars(result)
            if reported is None:
                reported = sorted(values)
                print(f"MPNN이 내놓은 스칼라: {reported or '없음'}", flush=True)
                print(f"결과 객체: {type(result).__name__}", flush=True)
            entry["mpnn"] = values
            designs.append(entry)
        print(f"  seed {seed}: 서열 {len(results)}개 (누적 {len(designs)})", flush=True)

    if len(designs) != SEQUENCES:
        raise RuntimeError(f"Expected {SEQUENCES} sequences, got {len(designs)}.")

    known = {entry["sequence"] for entry in
             read_json(REPOSITORY / SOURCE_RUN / "manifest.json")
             if entry["name"].startswith(f"{BACKBONE}_")}
    unique = {entry["sequence"] for entry in designs}
    overlap = unique & known
    print(f"서로 다른 서열 {len(unique)}/{len(designs)}개, "
          f"v0.2.0의 8개와 겹침 {len(overlap)}개", flush=True)

    write_json(root / "manifest.json",
               [{k: v for k, v in entry.items() if k in ("name", "design_pdb", "sequence")}
                for entry in designs])
    write_json(root / "mpnn_scores.json", designs)
    (root / "designs.fasta").write_text(
        "".join(f">{d['name']}\n{d['sequence']}\n" for d in designs), encoding="utf-8")
    print(f"설계 {len(designs)}개 완료", flush=True)


if __name__ == "__main__":
    stages = {stage.__name__: stage for stage in (prepare_backbone, design_sequences)}
    stages[sys.argv[1]](Path(sys.argv[2]))
