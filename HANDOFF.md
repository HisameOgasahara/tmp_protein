# GFP docking handoff

2026-11-17 · Executed notebook v0.1.9 · Implementation commit `de92f4f9f982faf5988b5675e8358acff605fedf`

## Current outcome

| Component | Verified outcome | Remaining work |
| --- | --- | --- |
| Enhancer folding | NanoBodyBuilder2 monomer RMSD 0.477 Å; RF3 complexes pass 3/3 with pose RMSD 0.956–1.145 Å | Evaluate transfer to additional inputs |
| Minimizer docking | MEGADOCK on T4 completes search in 7.27 seconds; original rank 2 has pose RMSD 0.989 Å | Integrate reference-independent candidate selection |
| Recovery assessment | Strengthened criteria reject incorrect rank 31 and accept rank 2 | Preserve assessment separately from candidate selection |

## Evidence and files

- [Run 07 analysis and action sequence](docs/2026-11-17-gfp-run07-analysis.md)
- [Run 07 original ZIP](results/07_gfp_diagnostics_1wx_7cqz/gfp_diagnostics_1wx_7cqz.zip), with complete structures and runtime logs inside
- [Recomputed atom distances for 100 poses](results/07_gfp_diagnostics_1wx_7cqz/minimizer_docking/metrics/clash_analysis.csv)
- [Clash cutoff sensitivity](results/07_gfp_diagnostics_1wx_7cqz/minimizer_docking/metrics/clash_threshold_sensitivity.json)
- [Run 06 comparison](docs/2026-11-17-gfp-run06-analysis.md)

Selected metrics, source metadata and timing files are also unpacked under each result directory. Historical outputs retain their original assessment fields.

## Findings that guide the next implementation

1. Enhancer's main observed failure occurred during standalone folding. NanoBodyBuilder2 already achieved 0.460 Å before refinement and 0.477 Å afterward. RF3 settings, seeds and native reference were identical across runs 06 and 07. All three complex seeds reused the same predicted monomer.
2. MEGADOCK produces a raw score ranking. `megadock_compare.py` measures clashes afterward and preserves that original ordering. Candidate selection currently lacks a clash-filtered ranking.
3. Applying the existing 2 Å minimum heavy-atom distance filter to the evaluated top 100 retains 27 poses. Original rank 2 becomes the first candidate using only predicted coordinates and MEGADOCK scores.
4. Original rank 1 contains three interchain heavy-atom pairs below 2 Å, with a minimum of 1.265 Å. Rank 2 has a minimum of 2.047 Å. Raising the cutoff to 2.05 Å discards rank 2; at 2.2 Å, incorrect rank 31 becomes first. Keep this sensitivity in view when designing selection.
5. Both runs contain identical rotations, translations and ordering for all 2,000 docking candidates. Maximum score variation is 0.02. The assessment change corrected the rank-31 false positive.
6. The cause of the raw score inversion remains unresolved. The saved output contains total scores; component contributions require a new detailed-output run. RF3's internal reason for poor sequence-only folding and NanoBodyBuilder2 generalization remain open.

## Next work in order

1. Implement candidate selection among the currently evaluated top 100 poses using the existing 2 Å clash filter, followed by original MEGADOCK score order. Record original rank, filtered rank, exclusion reason and selected candidate. Handle an empty eligible set explicitly.
2. Keep crystal-reference RMSD and contact recovery exclusively in downstream benchmark assessment. Selection must operate from predicted coordinates and scores. Verify that run 07 selects original rank 2.
3. Enable MEGADOCK `-O` output with the same inputs, 3,600 rotations and 1.2 Å grid. Compare rPSC, electrostatic and ACE contributions for ranks 1 and 2. The tool's internal RMSD uses the separated, rotated input frame; use the project's native-reference metrics for recovery assessment.
4. Reuse run 07's predicted Enhancer monomer with GFP to evaluate the same docking and selection procedure on another control. Assess the selected pose against its crystal structure afterward.
5. If problems remain, compare grid spacing or structural refinement one factor at a time and record both selection quality and runtime.

The current Minimizer docking uses monomers taken from its crystal structure. Performance with errors in newly predicted monomers still needs evaluation. Review both controls before extending the selection procedure to new candidates. Fluorescence estimates require experimental data in addition to structural assessment.

## Implementation entry points

| File | Responsibility |
| --- | --- |
| `gfp_pipeline/megadock_compare.py` | GPU search, pose reconstruction, metrics and raw ranked output |
| `gfp_pipeline/megadock_runtime.py` | Pinned source build and GPU environment |
| `gfp_pipeline/benchmark.py` | Shared structure metrics, recovery criteria and failure reasons |
| `gfp_pipeline/diagnostic_experiments.json` | Runtime settings and project thresholds |
| `gfp_pipeline/nanobody_fold.py` | NanoBodyBuilder2 prediction, refinement and sequence mapping |
| `gfp_pipeline/enhancer_split.py` | Predicted-monomer and crystal-monomer RF3 comparison |
| `gfp_pipeline/notebook_workflow.py` | Notebook jobs, result display and ZIP packaging |
| `tests/test_pose_recovery.py` | Four regression tests using run 06 structures |

Recovery requires GFP RMSD ≤ 3 Å, binder pose RMSD ≤ 5 Å, binder self-aligned RMSD ≤ 2 Å, GFP contact Jaccard ≥ 0.5, native residue-pair recovery ≥ 0.5, and no clash. These are project benchmark thresholds selected during v0.1.9 implementation.

## Resume and verification

Open [Colab v0.1.9](https://colab.research.google.com/github/HisameOgasahara/tmp_protein/blob/main/GFP_Binder_T4.ipynb?v=0.1.9) on a T4 runtime. Execute the first initialization cell before the settings cell. A missing `build_jobs` name indicates initialization has not completed.

Use `RUN_MODE=diagnostics` and `DIAGNOSTIC_EXPERIMENT=minimizer_docking` for the existing docking-only path, or `all` for both experiments. The proposed Enhancer MEGADOCK comparison requires implementation. The current Enhancer path runs NanoBodyBuilder2 followed by six RF3 complex predictions, taking about 17 minutes for those RF3 calls alone.

From the repository root on Windows, the existing regression command is `.venv\Scripts\python.exe -B -m unittest discover -s tests -v`. All four tests passed before the v0.1.9 push. Run 07 subsequently confirmed actual Colab NanoBodyBuilder2 and MEGADOCK execution. The next implementation should add coverage for selection order, all-candidates-excluded handling and separation from reference metrics.

MEGADOCK is licensed under CC BY-NC 4.0. The implementation uses pinned upstream source revisions and saves environment and model-weight provenance with results.
