# GFP 도킹 인계

2026-11-17 · 실행한 노트북 v0.1.9 · 구현 커밋 `de92f4f9f982faf5988b5675e8358acff605fedf`

## 현재 결과

| 항목 | 확인된 결과 | 남은 작업 |
| --- | --- | --- |
| Enhancer 접힘 | NanoBodyBuilder2 단량체 RMSD 0.477 Å; RF3 복합체 3/3 통과, 자세 RMSD 0.956–1.145 Å | 추가 입력에서도 성능이 유지되는지 평가 |
| Minimizer 도킹 | T4의 MEGADOCK 탐색 7.27초; 원래 2위의 자세 RMSD 0.989 Å | 기준 구조에 의존하지 않는 후보 선택 적용 |
| 자세 복원 평가 | 강화한 기준이 잘못된 31위를 탈락시키고 2위를 통과시킴 | 후보 선택과 평가를 분리하여 유지 |

## 근거와 파일

- [Run 07 분석과 작업 순서](docs/2026-11-17-gfp-run07-analysis.md)
- [Run 07 원본 ZIP](results/07_gfp_diagnostics_1wx_7cqz/gfp_diagnostics_1wx_7cqz.zip): 전체 구조와 실행 로그 포함
- [자세 100개의 원자 거리 재계산](results/07_gfp_diagnostics_1wx_7cqz/minimizer_docking/metrics/clash_analysis.csv)
- [충돌 거리 기준 민감도](results/07_gfp_diagnostics_1wx_7cqz/minimizer_docking/metrics/clash_threshold_sensitivity.json)
- [Run 06 비교](docs/2026-11-17-gfp-run06-analysis.md)

주요 지표, 소스 메타데이터와 실행 시간 파일은 각 결과 폴더에도 풀어 두었다. 과거 출력의 평가 필드는 원래 값으로 보존했다.

## 다음 구현의 근거

1. 관찰된 Enhancer의 주요 실패는 단독 접힘 단계에서 발생했다. NanoBodyBuilder2는 구조 정제 전부터 0.460 Å를 달성했고, 정제 후에는 0.477 Å였다. Run 06과 07의 RF3 설정, 시드와 기준 구조는 동일했다. 복합체 시드 3개는 같은 예측 단량체를 재사용했다.
2. MEGADOCK은 원점수 순위를 출력한다. `megadock_compare.py`는 이후 충돌을 측정하면서 원래 순서를 유지한다. 현재 후보 선택에는 충돌을 제외한 순위가 없다.
3. 평가한 상위 100개에 기존 중원자 최소 거리 2 Å 필터를 적용하면 27개가 남는다. 예측 좌표와 MEGADOCK 점수만으로 원래 2위가 첫 후보가 된다.
4. 원래 1위에는 사슬 간 중원자 거리가 2 Å 미만인 쌍이 3개 있고, 최소 거리는 1.265 Å다. 2위의 최소 거리는 2.047 Å다. 기준을 2.05 Å로 높이면 2위가 탈락하고, 2.2 Å에서는 잘못된 31위가 첫 후보가 된다. 선택 절차를 설계할 때 이 민감도를 고려한다.
5. 두 실행의 도킹 후보 2,000개 모두 회전, 이동과 순서가 동일하다. 최대 점수 차이는 0.02다. 평가 기준 변경으로 31위의 잘못된 통과를 바로잡았다.
6. 원점수 순위가 뒤집힌 원인은 아직 해결되지 않았다. 저장된 출력에는 총점이 있으며, 항목별 기여도는 상세 출력을 켜고 다시 실행해야 확인할 수 있다. RF3가 서열만으로 접힘을 예측할 때 실패한 내부 원인과 NanoBodyBuilder2의 일반화 성능도 미해결 상태다.

## 다음 작업 순서

1. 현재 평가하는 상위 100개에 기존 2 Å 충돌 필터를 적용하고, 원래 MEGADOCK 점수 순서로 후보를 선택하도록 구현한다. 원래 순위, 필터 적용 후 순위, 제외 사유와 최종 선택 후보를 기록한다. 적격 후보가 하나도 없는 경우도 명시적으로 처리한다.
2. 결정 구조 기준 RMSD와 접촉 복원 지표는 선택 후 벤치마크 평가에만 사용한다. 선택에는 예측 좌표와 점수만 사용한다. Run 07에서 원래 2위가 선택되는지 확인한다.
3. 같은 입력, 회전 3,600개, 격자 1.2 Å로 MEGADOCK `-O` 출력을 활성화한다. 1위와 2위의 rPSC, 정전기 및 ACE 기여도를 비교한다. 도구 내부 RMSD는 분리하고 회전시킨 입력 좌표계를 사용하므로, 자세 복원 평가는 프로젝트의 기준 구조 지표를 사용한다.
4. Run 07의 예측 Enhancer 단량체와 GFP를 재사용해 다른 대조군에서도 같은 도킹 및 선택 절차를 평가한다. 선택한 자세를 이후 결정 구조와 비교한다.
5. 문제가 남으면 격자 간격이나 구조 정제를 한 번에 한 요소씩 비교하고, 선택 품질과 실행 시간을 함께 기록한다.

현재 Minimizer 도킹은 결정 구조에서 가져온 단량체를 사용한다. 새로 예측한 단량체에 오차가 있을 때의 성능은 추가 평가가 필요하다. 새 후보로 선택 절차를 확장하기 전에 두 대조군을 검토한다. 형광 추정에는 구조 평가 외에 실험 데이터가 필요하다.

## 구현 진입점

| 파일 | 역할 |
| --- | --- |
| `gfp_pipeline/megadock_compare.py` | GPU 탐색, 자세 재구성, 지표와 원점수 순위 출력 |
| `gfp_pipeline/megadock_runtime.py` | 고정한 소스 버전의 빌드와 GPU 환경 |
| `gfp_pipeline/benchmark.py` | 공통 구조 지표, 복원 기준과 실패 사유 |
| `gfp_pipeline/diagnostic_experiments.json` | 실행 설정과 프로젝트 임계값 |
| `gfp_pipeline/nanobody_fold.py` | NanoBodyBuilder2 예측, 정제와 서열 매핑 |
| `gfp_pipeline/enhancer_split.py` | 예측 단량체와 결정 구조 단량체의 RF3 비교 |
| `gfp_pipeline/notebook_workflow.py` | 노트북 작업, 결과 표시와 ZIP 패키징 |
| `tests/test_pose_recovery.py` | Run 06 구조를 이용하는 회귀 테스트 4개 |

복원 통과 조건은 GFP RMSD ≤ 3 Å, 바인더 자세 RMSD ≤ 5 Å, 바인더 자체 정렬 RMSD ≤ 2 Å, GFP 접촉 Jaccard ≥ 0.5, 기준 구조 잔기 쌍 복원율 ≥ 0.5, 충돌 없음이다. v0.1.9 구현 과정에서 정한 프로젝트 벤치마크 임계값이다.

## 재개와 확인

T4 런타임에서 [Colab v0.1.9](https://colab.research.google.com/github/HisameOgasahara/tmp_protein/blob/main/GFP_Binder_T4.ipynb?v=0.1.9)를 연다. 설정 셀 전에 첫 초기화 셀을 실행한다. `build_jobs` 이름이 없다는 오류는 초기화가 완료되지 않았음을 나타낸다.

기존 도킹만 실행하려면 `RUN_MODE=diagnostics`, `DIAGNOSTIC_EXPERIMENT=minimizer_docking`을 사용하고, 두 실험을 모두 실행하려면 `all`을 사용한다. 제안한 Enhancer MEGADOCK 비교는 구현이 필요하다. 현재 Enhancer 경로는 NanoBodyBuilder2 이후 RF3 복합체 예측을 6회 실행하며, 이 RF3 호출에만 약 17분이 걸린다.

Windows 저장소 루트에서 기존 회귀 테스트 명령은 `.venv\Scripts\python.exe -B -m unittest discover -s tests -v`다. v0.1.9 푸시 전에 테스트 4개가 모두 통과했다. 이후 Run 07에서 Colab의 NanoBodyBuilder2와 MEGADOCK 실제 실행을 확인했다. 다음 구현에서는 선택 순서, 전체 후보 제외 처리와 기준 구조 지표로부터의 분리를 검증하는 항목을 추가한다.

MEGADOCK의 라이선스는 CC BY-NC 4.0이다. 구현은 고정한 업스트림 소스 리비전을 사용하며, 환경과 모델 가중치 출처를 결과와 함께 저장한다.
