# GFP 실행 05: 결합 자세 탐색과 결합체 접힘의 분리

2026-11-17 · 실행 버전 v0.1.6 · 커밋 `a6926ef` · 후속 구현 v0.1.7

Minimizer는 두 단백질의 개별 구조를 제공하고 시드를 10개로 늘려도 결합 자세를 회복하지 못했다. Enhancer는 결합체 템플릿을 제거하자 개별 접힘과 결합 자세가 모두 기준 구조에서 벗어났다. 새 후보의 결합 구조를 평가하려면 접힘과 상대 배치의 실패를 분리해야 한다.

## 실행 조건과 결과

| 지표 | Minimizer 시드 확대 | Enhancer 템플릿 제거 |
| --- | --- | --- |
| 제공 구조 | GFP·결합체 (`both`) | GFP만 (`target`) |
| Recycles / diffusion steps | 10 / 50 | 10 / 50 |
| 시드 | 0–9 | 0, 1, 2 |
| 기존 결합면 회복 기준 통과 | 0/10 | 0/3 |
| GFP 정렬 후 결합체 Cα RMSD | 29.986–40.178 Å | 24.459–33.892 Å |
| 최고 GFP 접촉면 Jaccard | 0.083 | 0.136 |
| 최고 기준 잔기 쌍 접촉 회복률 | 8.57% | 0% |
| 최고 ipTM | 0.259 | 0.197 |
| 충돌 판정 | 시드 5에서 발생 | 없음 |
| 결합체 자체 정렬 Cα RMSD | 0.083–0.100 Å | 6.843–8.712 Å |
| 추론 시간 합계 | 약 32.7분 | 약 9.0분 |

[실험 목록·실행 커밋](../results/05_gfp_followup_4njwiy3c/experiments.json) · [Minimizer 지표](../results/05_gfp_followup_4njwiy3c/minimizer_seed_search/metrics/benchmark_poses.csv) · [Enhancer 지표](../results/05_gfp_followup_4njwiy3c/enhancer_target_only/metrics/benchmark_poses.csv)

기존 회복 기준은 GFP Cα RMSD ≤ 3 Å, GFP 접촉면 Jaccard ≥ 0.5, 충돌 없음이다. 잔기 쌍 접촉은 Cα 거리 8 Å 이하로 집계했다. 결합체 자체 RMSD는 저장된 CIF와 참조 JSON의 동일 관측 잔기를 대응시켜 결합체만 최적 정렬한 추가 계산이다. 13개 예측은 모두 정상 종료됐다.

## 원인 판단

Minimizer의 자체 구조 오차는 작지만 GFP 기준 결합체 오차는 크다. 이번 조건에서 형태 보존은 작동했고 상대 배치 탐색은 실패했다. 평가된 10개 자세에 기준 회복 자세가 없으므로 순위 조정만으로 이번 결과를 해결할 수 없다. 더 많은 시드에서도 반드시 실패한다는 결론까지는 뒷받침하지 않는다.

Enhancer는 [실행 04](2026-11-17-gfp-run04-analysis.md)의 두 구조 제공 조건에서 3/3 성공했으나 이번 GFP만 제공한 조건에서는 0/3이다. 결합체 자체 RMSD도 약 0.08 Å에서 6.84–8.71 Å로 커졌다. 결합체 구조 제공의 효과가 드러났지만, 단독 접힘의 실패와 복합체 예측 중 변형을 이번 출력만으로 분리할 수는 없다.

## v0.1.7 비교 실험

| 실험 | 입력과 절차 | 판단할 사항 |
| --- | --- | --- |
| `enhancer_split` | 서열만으로 enhancer 단독 예측 → 예측된 enhancer 구조와 GFP 구조로 복합체 예측 → 결정 구조 enhancer를 제공한 대조 조건과 비교 | 단독 접힘 오류인지, 개별 구조를 제공해도 남는 배치 오류인지 |
| `minimizer_docking` | 실행 05의 동일한 개별 참조 구조를 분리·회전 → LightDock 강체 탐색 → 군집화 → 점수 상위 대표 자세 평가 | RF3 이외의 탐색·점수화에서 결합 자세를 회복하는지 |

Enhancer는 시드 0·1·2마다 단독 예측 1회와 복합체 예측 2회를 수행한다. 복합체의 두 조건은 난수 시드를 동일하게 다시 설정하고, 최종 평가는 모두 원래 결정 구조를 기준으로 한다. 예측된 결합체 구조를 제공한 결과의 평가 기준을 그 예측 구조로 바꾸지 않는다. RF3는 recycle 10회, diffusion 50 steps, 샘플 1개를 유지한다.

Minimizer는 원래 두 체인의 상대 배치와 접촉 제한을 입력에서 제거한다. LightDock 0.9.4의 `fastdfire`, 자동 표면 swarm 배치, swarm당 200 glowworms, 100 steps를 사용한다. ANM 변형은 사용하지 않는 강체 비교다. [공식 기본 절차](https://lightdock.org/tutorials/0.9.3/basics)의 구조 생성·군집화 후 점수 순위를 적용하며 상위 최대 100개 대표 자세를 평가한다. 따라서 결과의 실패 범위는 평가한 상위 대표 자세에 한정한다.

도킹 결과에는 GFP 정렬 후 결합체 RMSD, GFP 접촉면 Jaccard, 잔기 쌍 회복률과 원자 충돌을 기록한다. LightDock 쪽 충돌은 서로 다른 체인의 비수소 원자 최소 거리가 2 Å 미만인 경우로 정의한다. 이는 RF3의 내장 충돌 판정과 다른 기준이므로 각 결과에 판정 방법을 함께 기록한다. LightDock 점수와 RF3 ipTM의 숫자 크기를 직접 비교하지 않는다.

## 실행과 결과 보존

[통합 노트북 v0.1.7](../GFP_Binder_T4.ipynb)에서 `RUN_MODE=diagnostics`를 선택한다. `DIAGNOSTIC_EXPERIMENT=all`은 enhancer 분리 실험 후 minimizer 도킹을 실행하며, 각 실험을 따로 선택할 수도 있다. LightDock은 CPU를 사용하고 RF3는 T4 GPU를 사용한다. 자동 swarm 수에 따라 도킹 시간이 달라지며 v0.1.6의 약 40분 추론 시간을 그대로 적용할 수 없다.

LightDock은 RF3와 분리된 Python 3.10 환경에서 실행한다. 공식 PyPI 배포의 안정 버전 0.9.4와 이에 맞춘 의존성을 [실험 설정](../gfp_pipeline/diagnostic_experiments.json)에 고정한다. 환경별 실제 패키지 목록은 `runtime/packages.json`, 상세 로그는 `runtime/`에 남긴다. 같은 Colab 세션에서는 완성된 모델 가중치와 설치 환경을 재사용한다.

Minimizer의 탐색 좌표·설정·군집·순위는 `docking/`, 평가한 상위 구조는 `structures/`, 자세 지표는 `metrics/docking_poses.csv`에 저장한다. 군집화 중 생성한 전체 PDB는 군집화 직후 제거하며, 각 자세를 재생성할 수 있는 GSO 좌표와 입력 구조를 보존한다. Enhancer의 단독·복합체 구조와 지표는 `structures/`, `metrics/enhancer_split.csv`에 저장한다. 마지막 셀에서 완료된 실험들을 하나의 ZIP으로 내려받는다.

[실행 05 전용 폴더](../results/05_gfp_followup_4njwiy3c)에는 기존 두 실험의 구조·설정·지표·로그와 [원본 ZIP](../results/05_gfp_followup_4njwiy3c/gfp_followup_4njwiy3c.zip)을 그대로 보존한다. v0.1.7의 실제 GPU·전체 도킹 결과는 아직 없다.
