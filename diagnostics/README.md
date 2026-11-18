# 진단

결과가 기대와 다를 때 원인을 한 요소씩 좁히는 조건 비교 실험. 일반 실행(`notebooks/`)과
분리한 이유 — 느리고(AF2 여러 회), 실패해도 끝까지 돌려야 하며, 지표가 아니라 입력 배열까지
저장해야 함.

## 설계 원칙

- 기준 조건 하나를 정하고 한 번에 한 항목만 변경.
- 조건마다 별도 프로세스. 하나가 실패해도 나머지 계속 진행.
- 같은 조건을 두 번 넣어 재현성 확인 (`*_repeat`).
- 정답 좌표를 쓰는 조건은 대조군으로 명시하고 입력 차이를 표에 기재.
- 원시 특징·전처리 특징·초기 좌표·모델 설정·신뢰도 배열을 전부 저장하고 기준 조건과 배열
  단위로 비교 (`feature_differences.json`).

마지막 항목이 결정적 — "무엇이 달랐나"를 추측이 아니라 배열 차이로 확인.

## [90_af2_conditions_T4.ipynb](90_af2_conditions_T4.ipynb) — AF2 재현 실패 원인 분리

코드: [diagnostic_workflow.py](../src/af2_filter/diagnostic_workflow.py) ·
[diagnostic_case.py](../src/af2_filter/diagnostic_case.py) ·
소요: AF2 11회, 23분 (조건당 122–148초)

기준 조건: 원본 방식 서열 입히기 · 시드 0 · recycle 3 · initial guess 사용 · 표적 템플릿
사용 · JAX 기본 정밀도.

| 조건 | 바꾼 항목 | 설계 기준 RMSD | `pae_interaction` |
| --- | --- | --- | --- |
| `original_thread` | (기준) | 32.780 Å | 26.15 |
| `original_thread_repeat` | 없음 — 재현성 확인 | 32.780 Å | 26.15 |
| `mutate_baseline` | 서열 입히기 방식 | 32.780 Å | 26.15 |
| `highest_precision` | JAX 행렬곱 정밀도 | 32.780 Å | 26.15 |
| `seed_1` | 시드 1 | 39.346 Å | 26.32 |
| `seed_2` | 시드 2 | 24.192 Å | 25.77 |
| `recycles_12` | recycle 12회 | 40.216 Å | 26.42 |
| `no_initial_guess` | initial guess 해제 | 48.829 Å | 26.51 |
| `empty_target_template` | 표적 템플릿 좌표·마스크 0 | 45.696 Å | 25.57 |
| `grafted_target_sidechains` | 1WWW 체인 X에서 사이드체인 이식 (**수정안**) | **1.496 Å** | **5.86** |
| `published_coordinates_control` | 공개 AF2 복합체 좌표 투입 | **1.648 Å** | **4.86** |
| `published_target_control` | 공개 AF2의 표적 원자만 투입 | **1.654 Å** | **4.86** |

v0.1.0 실행은 `grafted_target_sidechains`를 제외한 11조건이고 값이 동일
(`recycles_12`만 40.216 → 40.204 Å). v0.2.0 기록:
[results/2026-11-18-trka88-diagnostics-v2](../results/2026-11-18-trka88-diagnostics-v2)

읽는 법:

- 위 9조건은 모두 설계 좌표에서 출발하고 모두 실패. 탐색 설정(시드·recycle·정밀도)과
  입력 준비 방식을 바꿔도 실패 범위를 벗어나지 않음.
- 같은 시드에서 32.780 Å이 재현되므로 비결정성·수치 정밀도 문제가 아님.
- 통과하는 세 조건의 공통점은 표적 좌표를 실제 구조에서 가져온 것.
- `published_target_control`은 결합체에 설계 좌표를 그대로 쓰고 표적 원자만 교체한 조건.
  이것이 통과하므로 원인이 결합체 설계가 아니라 표적 입력으로 분리됨.

## 수정안 판정

`grafted_target_sidechains` — 실험 구조(1WWW 체인 X, 서열 동일)에서 사이드체인을 잔기별로
이식. 설계 주사슬 편차 0.000000 Å, 표적 사이드체인 중원자 378개 충전.

1.496 Å / PAE 5.86으로 정답 좌표 투입 대조군(1.654 Å / 4.86)과 같은 영역. 공개 AF2
구조와의 차이 0.191 Å로 대조군(0.409·0.412 Å)보다 작음 — 대조군은 AF2 자신의 예측을
되먹인 것이고 이쪽은 독립적인 결정 구조.

## 배열 비교로 확정한 것

입력 특징 배열을 실패 기준(`original_thread`)과 비교하면 이식 조건의
`template_pseudo_beta`(CB 위치) 최대 차이가 **0.202 Å**. `published_target_control`은
같은 값이 1.425 Å.

설계 주사슬이 그대로이고 CB도 사실상 제자리인데 **CB 바깥 사이드체인 원자만 바뀌어
32.780 Å이 1.496 Å이 됨.** 이전 대조군은 주사슬과 CB를 함께 움직여 원인을 사이드체인으로
좁힐 수 없었음.
[문제 기록](../docs/issues/2026-11-18-trka-target-sidechains.md)
