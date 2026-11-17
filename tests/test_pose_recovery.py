import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "gfp_pipeline"))

from benchmark import build_chain_reference, measure_pose, pose_failure_reasons, recovery_criteria
from lightdock_compare import read_pose, write_partner
from nanobody_fold import evaluate_fold


class PoseRecoveryRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = ZipFile(REPO / "results/06_gfp_diagnostics_57r1lsl_/gfp_diagnostics_57r1lsl_.zip")
        cls.settings = json.loads((REPO / "gfp_pipeline/diagnostic_experiments.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.archive.close()

    def test_actual_megadock_structures_keep_rank_two_and_reject_rank_31(self):
        native = json.loads(self.archive.read("minimizer_docking/config/reference_minimizer.json"))
        accepted = []
        with tempfile.TemporaryDirectory() as directory:
            for rank in range(1, 101):
                path = Path(directory) / "pose.pdb"
                path.write_bytes(self.archive.read(f"minimizer_docking/structures/top_{rank}.pdb"))
                target, binder, clash = read_pose(path, native, self.settings["docking"]["heavy_atom_clash_distance_angstrom"])
                row = {**measure_pose(target, binder, native, self.settings["contact_radius_angstrom"]), **clash}
                failures = pose_failure_reasons(row, self.settings)
                if not failures:
                    accepted.append(rank)
                if rank == 31:
                    self.assertIn("binder_ca_rmsd_after_target_alignment_angstrom", failures)
                    self.assertIn("native_ca_contact_pair_recovery", failures)
        self.assertEqual(accepted, [2])

    def test_enhancer_bad_folds_fail_and_crystal_controls_pass(self):
        rows = json.loads(self.archive.read("enhancer_split/metrics/diagnostic_summary.json"))["rows"]
        for row in rows:
            if row["stage"] == "predicted_binder":
                self.assertIn("binder_self_rmsd_angstrom", pose_failure_reasons(row, self.settings))
            elif row["stage"] == "crystal_binder":
                self.assertEqual(pose_failure_reasons(row, self.settings), [])

    def test_missing_nonfinite_and_boundary_values(self):
        c = recovery_criteria(self.settings)
        previous = json.loads(self.archive.read("minimizer_docking/config/diagnostics.json"))
        self.assertEqual(recovery_criteria(previous), c)
        row = dict(target_ca_rmsd_angstrom=c["max_target_rmsd_angstrom"],
                   binder_ca_rmsd_after_target_alignment_angstrom=c["max_binder_pose_rmsd_angstrom"],
                   binder_self_rmsd_angstrom=c["max_binder_self_rmsd_angstrom"],
                   benchmark_contact_jaccard=c["min_contact_jaccard"],
                   native_ca_contact_pair_recovery=c["min_native_contact_pair_recovery"], has_clash=False)
        self.assertEqual(pose_failure_reasons(row, self.settings), [])
        for metric in row:
            incomplete = dict(row)
            incomplete.pop(metric)
            self.assertTrue(pose_failure_reasons(incomplete, self.settings))
        row["binder_self_rmsd_angstrom"] = float("nan")
        self.assertTrue(pose_failure_reasons(row, self.settings))

    def test_nanobody_sequence_mapping_and_missing_residue(self):
        native = json.loads(self.archive.read("enhancer_split/config/reference_enhancer.json"))["binder"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nanobody.pdb"
            write_partner(path, native, "H", np.random.default_rng(7))
            mapped = build_chain_reference(path.read_text().splitlines(), "H", native["sequence"])
            self.assertLess(evaluate_fold(mapped, native), 0.001)
        incomplete = copy.deepcopy(mapped)
        index = next(atom["index"] for atom in incomplete["atoms"] if atom["atom"] == "CA")
        incomplete["atoms"] = [atom for atom in incomplete["atoms"] if atom["index"] != index]
        with self.assertRaises(ValueError):
            evaluate_fold(incomplete, native)


if __name__ == "__main__":
    unittest.main()
