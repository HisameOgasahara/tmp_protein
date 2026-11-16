import json
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path
from tempfile import mkdtemp
from zipfile import ZIP_DEFLATED, ZipFile


def build_jobs(checkout, mode, diagnostic="all", followup="all", template="both", recycles=10,
               seeds="0,1,2", assay=""):
    checkout = Path(checkout)
    if mode == "diagnostics":
        settings = json.loads((checkout / "gfp_pipeline/diagnostic_experiments.json").read_text(encoding="utf-8"))
        selected = [name for name in settings["experiments"] if diagnostic == "all" or name == diagnostic]
        if not selected:
            raise ValueError("진단 실험을 선택하세요.")
        return [{"id": name, "label": name, "runner": "diagnostics.py",
                 "args": ["--experiment", name], "experiment": {"id": name}}
                for name in selected]
    if mode == "followup":
        settings = json.loads((checkout / "gfp_pipeline/benchmark_experiments.json").read_text(encoding="utf-8"))
        selected = [item for item in settings["experiments"] if followup == "all" or item["id"] == followup]
        if not selected:
            raise ValueError("후속 실험을 선택하세요.")
        return [{"id": item["id"], "label": item["label"], "runner": "run.py", "experiment": item,
                 "args": ["--benchmark-only", "--benchmark-controls", item["control"],
                          "--benchmark-template", item["template"], "--benchmark-recycles", str(item["recycles"]),
                          "--benchmark-seeds", *map(str, item["seeds"])]} for item in selected]
    if mode == "benchmark":
        values = [int(value.strip()) for value in seeds.split(",")]
        args = ["--benchmark-only", "--benchmark-template", template,
                "--benchmark-recycles", str(recycles), "--benchmark-seeds", *map(str, values)]
    elif mode == "full":
        args = ["--assays", str(Path(assay).expanduser().resolve(strict=True))] if assay.strip() else []
    else:
        raise ValueError("실행 모드를 선택하세요.")
    return [{"id": mode, "label": mode, "runner": "run.py", "args": args, "experiment": {"id": mode}}]


def run_jobs(checkout, revision, jobs, completed_runs, output_parent="/content"):
    session = Path(mkdtemp(prefix="gfp_session_", dir=output_parent))
    for job in jobs:
        log = session / f"{job['id']}.log"
        print(f"실행: {job['label']} · 상세 로그: {log}", flush=True)
        command = [sys.executable, str(Path(checkout) / "gfp_pipeline" / job["runner"]),
                   "--revision", revision, *job["args"]]
        result_zip = None
        with log.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(command) + "\n")
            with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding="utf-8", errors="replace") as process:
                for line in process.stdout:
                    handle.write(line)
                    handle.flush()
                    if line.rstrip().endswith(".zip"):
                        result_zip = Path(line.strip())
                code = process.wait()
        if code:
            with log.open(encoding="utf-8") as handle:
                print("".join(deque(handle, maxlen=40)))
            raise RuntimeError(f"{job['id']}: 실행 실패. 전체 로그: {log}")
        if result_zip is None or not result_zip.is_file():
            raise RuntimeError(f"결과 ZIP을 찾을 수 없습니다. 전체 로그: {log}")
        result_dir = result_zip.with_suffix("")
        shutil.copyfile(log, result_dir / "runtime/notebook.log")
        # Include the notebook transcript in the single-run ZIP as well.
        with ZipFile(result_zip, "a", compression=ZIP_DEFLATED) as archive:
            archive.write(log, "runtime/notebook.log")
        completed_runs.append({"experiment": job["experiment"], "result_zip": result_zip, "result_dir": result_dir})
        print(f"완료: {job['label']} · {result_zip.name}", flush=True)


def display_results(checkout, mode, completed_runs):
    import pandas as pd
    from IPython.display import display

    if mode == "diagnostics":
        for run in completed_runs:
            root = run["result_dir"]
            summary = json.loads((root / "metrics/diagnostic_summary.json").read_text(encoding="utf-8"))
            baseline = json.loads((root / "config/baseline_summary.json").read_text(encoding="utf-8"))
            print(summary["experiment"], "· 실행 05 비교 기준")
            display(pd.DataFrame(baseline["controls"])[[
                "control", "poses_tested", "poses_recovered", "top_iptm_binder_rmsd_angstrom",
                "best_binder_rmsd_angstrom", "best_native_ca_contact_pair_recovery"]].round(3))
            if summary["experiment"] == "minimizer_docking":
                print(f"도킹 상위 {summary['poses_evaluated']}개 평가 · 접촉 기준 통과 {summary['contact_criterion_passed']}개")
                print("상위 10개 표시. 전체 평가는 metrics/docking_poses.csv에 저장됩니다.")
                display(pd.DataFrame(summary["rows"]).head(10).round(3))
            else:
                display(pd.DataFrame(summary["rows"]).round(3))
        return
    if mode == "followup":
        settings = json.loads((Path(checkout) / "gfp_pipeline/benchmark_experiments.json").read_text(encoding="utf-8"))
        baseline = json.loads((Path(checkout) / settings["baseline_summary"]).read_text(encoding="utf-8"))
        comparison = []
        for run in completed_runs:
            current = json.loads((run["result_dir"] / "metrics/benchmark_summary.json").read_text(encoding="utf-8"))
            for label, report in (("실행 04", baseline), (run["experiment"]["id"], current)):
                comparison.extend({"run": label, "template": report["template_mode"], **row}
                                  for row in report["controls"] if row["control"] == run["experiment"]["control"])
            display(pd.read_csv(run["result_dir"] / "metrics/benchmark_poses.csv").round(3))
        display(pd.DataFrame(comparison).round(3))
        return
    root = completed_runs[0]["result_dir"]
    if mode == "benchmark":
        display(pd.read_csv(root / "metrics/benchmark_summary.csv").round(3))
        display(pd.read_csv(root / "metrics/benchmark_poses.csv").round(3))
        return
    report = json.loads((root / "metrics/fluorescence_model.json").read_text(encoding="utf-8"))
    labels = {
        "ready": "형광 모델 검증 통과", "structural_benchmark_failed": "대조군 구조 검증 미통과",
        "insufficient_control_groups": "독립 실험 그룹 부족", "baseline_not_improved": "기준 모델 대비 개선 없음",
        "candidate_structure_failed": "후보 구조 검증 미통과", "outside_training_range": "접촉 특징이 학습 범위 밖",
        "outside_observed_effect_range": "예측값이 관측 범위 밖", "predicted": "예측값 산출",
    }
    print(labels[report["validation"]])
    for name in ("held_out_mae_log2", "no_effect_mae_log2"):
        if name in report:
            print(name, round(report[name], 3))
    frame = pd.read_csv(root / "metrics/fluorescence_predictions.csv")
    frame["prediction_status"] = frame["prediction_status"].map(labels)
    frame["predicted_fluorescence_ratio"] = frame["predicted_fluorescence_ratio"].round(3).astype(object).where(
        frame["predicted_fluorescence_ratio"].notna(), "보류")
    display(frame[["id", "iptm", "prediction_status", "predicted_fluorescence_ratio"]])


def package_results(revision, mode, completed_runs, output_parent="/content"):
    if not completed_runs:
        raise ValueError("완료된 실험이 없습니다.")
    if mode in ("full", "benchmark"):
        return completed_runs[0]["result_zip"]
    bundle = Path(mkdtemp(prefix=f"gfp_{mode}_", dir=output_parent)).with_suffix(".zip")
    manifest = {"revision": revision, "mode": mode,
                "runs": [{"experiment": run["experiment"], "original_zip": run["result_zip"].name}
                         for run in completed_runs]}
    with ZipFile(bundle, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("experiments.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for run in completed_runs:
            for path in sorted(run["result_dir"].rglob("*")):
                if path.is_file():
                    archive.write(path, (Path(run["experiment"]["id"]) / path.relative_to(run["result_dir"])).as_posix())
    return bundle
