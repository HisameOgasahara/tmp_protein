import csv
import json
import math
import os
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter

import numpy as np
import torch
from residues import AA

ROOT = Path(os.environ["DESIGN_RUN"])

def json_ready(value):
    if isinstance(value, (np.generic, np.ndarray)):
        return json_ready(value.tolist())
    if isinstance(value, torch.Tensor):
        return json_ready(value.detach().cpu().tolist())
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value

def write_json(path, value):
    path.write_text(json.dumps(json_ready(value), indent=2, ensure_ascii=False, allow_nan=False))

def write_csv(path, rows):
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

@contextmanager
def measure(model, operation, input_id):
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    baseline = torch.cuda.memory_allocated()
    start = perf_counter()
    status = "failed"
    try:
        yield
        torch.cuda.synchronize()
        status = "success"
    finally:
        row = dict(
            model=model, operation=operation, input_id=input_id, status=status,
            seconds=perf_counter() - start,
            baseline_allocated_mib=baseline / 2**20,
            peak_allocated_mib=torch.cuda.max_memory_allocated() / 2**20,
            peak_reserved_mib=torch.cuda.max_memory_reserved() / 2**20,
        )
        with (ROOT / "runtime/timings.jsonl").open("a") as handle:
            handle.write(json.dumps(row) + "\n")
        print(row, flush=True)

def save_cif(atoms, path):
    from atomworks.io.utils.io_utils import to_cif_file
    to_cif_file(atoms, path.with_suffix(""), file_type="cif")
    if not path.is_file():
        raise FileNotFoundError(path)

def load_cif(path):
    from biotite.structure.io import pdbx
    return pdbx.get_structure(pdbx.CIFFile.read(path), model=1)
