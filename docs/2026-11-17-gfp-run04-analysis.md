# GFP 실행 04: enhancer 자세 회복과 minimizer 배치 오류

2026-11-17 · v0.1.5 · 실행 커밋 `d5f4336` · `gfp_binder_1tsmdhg9`

Enhancer는 세 시드 모두에서 기준 결합 자세에 가깝게 예측됐다. Minimizer는 개별 단백질 형태를 보존했지만 GFP에 대한 위치·방향이 크게 달랐다. 두 대조군 전체의 자세 재현 조건은 아직 확보되지 않았다.

## 실행 조건

| 항목 | 값 |
| --- | --- |
| GFP·결합체 구조 | 각 대조군의 결정 구조에서 개별 템플릿 제공 (`both`) |
| 참조 구조 | enhancer 3K1K A/C, minimizer 3G9A A/B |
| 체인 간 정답 거리 | 입력 특징에서 차단 |
| RF3 설정 | recycle 10회, diffusion 50 steps, 시드당 샘플 1개 |
| 시드 | 0, 1, 2 |
| 추론 완료 | 6/6, 합계 약 17.8분 |
| 최대 예약 GPU 메모리 | 약 8.76 GiB |

[실행 설정](../results/04_gfp_binder_1tsmdhg9/config/source.json) · [시간·메모리 기록](../results/04_gfp_binder_1tsmdhg9/runtime/timings.jsonl) · [원본 ZIP](../results/04_gfp_binder_1tsmdhg9/gfp_binder_1tsmdhg9.zip)

## 대조군별 결과

| 지표 | Enhancer | Minimizer |
| --- | --- | --- |
| 기존 회복 기준 통과 | 3/3 | 0/3 |
| GFP Cα RMSD | 0.078–0.081 Å | 0.075–0.077 Å |
| GFP 정렬 후 결합체 Cα RMSD | 0.697–0.874 Å | 35.814–38.750 Å |
| GFP 접촉면 Jaccard | 1.000 | 0–0.087 |
| 기준 Cα 잔기 쌍 접촉 회복률 | 93.75–95.83% | 0–8.57% |
| 최고 ipTM | 0.936 | 0.259 |
| 충돌 판정 | 세 시드 모두 없음 | 세 시드 모두 없음 |

기존 회복 기준은 GFP RMSD ≤ 3 Å, GFP 접촉면 Jaccard ≥ 0.5, 충돌 없음이다. 접촉은 Cα 간 거리 8 Å 이하로 계산했다. Enhancer는 이 기준뿐 아니라 결합체 위치·방향 오차와 잔기 쌍 접촉에서도 기준 자세와 가까웠다.

[대조군 요약](../results/04_gfp_binder_1tsmdhg9/metrics/benchmark_summary.json) · [시드별 자세](../results/04_gfp_binder_1tsmdhg9/metrics/benchmark_poses.csv)

## Minimizer의 남은 문제

저장된 CIF와 `config/reference_*.json` 좌표를 비교하면 결합체 자체를 따로 정렬한 Cα RMSD는 enhancer 0.080–0.084 Å, minimizer 0.084–0.099 Å다. 개별 형태를 보존하는 템플릿은 두 대조군 모두에서 작동했다.

GFP를 정렬한 좌표계에서 minimizer의 관측 Cα 중심은 기준 위치에서 28.32–33.86 Å 떨어져 있다. 따라서 이번 minimizer 실패는 개별 형태보다 상대 배치에서 두드러진다. 세 시드만으로 샘플 탐색 부족과 모델의 결합 자세 선호를 구분할 수는 없다.

추가 계산은 [저장된 구조](../results/04_gfp_binder_1tsmdhg9/structures)와 [minimizer 참조 좌표](../results/04_gfp_binder_1tsmdhg9/config/reference_minimizer.json)의 동일 관측 잔기를 대응시켰다. 자체 RMSD는 결합체만 최적 정렬하고, 중심 이동 거리는 GFP의 정렬 변환을 결합체에 적용해 계산했다.

## 이전 실행과의 비교

| 항목 | 실행 03 | 실행 04 |
| --- | --- | --- |
| Enhancer 기준 통과 | 0/3 | 3/3 |
| Minimizer 기준 통과 | 0/3 | 0/3 |
| 결합체 템플릿 | 없음 | 제공 |
| GFP 템플릿 | 두 대조군 모두 3G9A | 각 대조군의 결정 구조 |
| Recycles | 3 | 10 |

[실행 03 요약](../results/03_gfp_binder_z0su7_po/metrics/benchmark_summary.json)과 비교하면 enhancer가 개선됐다. 여러 입력 조건이 함께 바뀌었으므로 개별 변경의 기여도는 분리되지 않았다. 이번 결과는 결합 상태에서 얻은 개별 구조를 이용한 재도킹이며, 새 설계 서열의 결합 성공을 입증하지 않는다.

## 후속 실험

| 실험 | 대조군 | 구조 조건 | Recycles | 시드 | 판단할 사항 |
| --- | --- | --- | --- | --- | --- |
| 시드 확대 | minimizer만 | `both` | 10 | 0–9 | 더 넓은 탐색에서 기준 자세가 생성되는가 |
| 결합체 템플릿 제거 | enhancer만 | `target` | 10 | 0, 1, 2 | GFP 구조만 제공해도 자세를 회복하는가 |

[후속 실험 노트북](../GFP_Benchmark_Followup_T4.ipynb)은 기본적으로 두 실험을 순서대로 실행한다. 각 실험은 별도 결과 폴더와 ZIP을 만들며, 기존 실행 04와 나란히 요약을 표시한다. 마지막 셀은 실험별 하위 폴더와 실행 목록을 하나의 ZIP으로 묶어 내려받는다. 단독 대조군 실행은 기존 두 대조군 연속 실행과 난수 소비 순서가 달라질 수 있으므로 같은 시드 번호가 같은 예측 좌표를 보장하지 않는다.

- Minimizer에서 정확한 자세가 생성되면 해당 자세의 ipTM 순위까지 확인한다. 10개 시드에서도 실패하면 동일 개별 구조를 이용한 단백질–단백질 도킹 비교가 다음 단계다.
- Enhancer가 `target` 조건에서도 성공하면 결합체 템플릿이 필수인지 재평가한다. 실패하면 결합체 구조 제공이 현재 조건에서 도움이 된다는 근거가 된다.
