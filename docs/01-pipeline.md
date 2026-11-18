# 설계문서 — 파이프라인 단계와 지표

## 단계

| 순서 | 도구 | 하는 일 | 코드 |
| --- | --- | --- | --- |
| 1 | RFdiffusion3 | 표적 hotspot에 접근하는 결합체 백본 생성 | [src/rfd3_design/](../src/rfd3_design/) |
| 2 | LigandMPNN / ProteinMPNN | 백본에 맞는 아미노산 서열 설계 | [src/rfd3_design/](../src/rfd3_design/) |
| 3 | AlphaFold2 initial guess | 복합체 예측 후 채점 | [src/af2_filter/](../src/af2_filter/) |
| 4 | — | 통과 후보를 실험으로 검증 | 범위 밖 |

1·2가 설계, 3이 채점이다. 3은 설계를 만들지 않고 판정만 한다.

## 3단계의 입력 구성

업스트림 `af2_initial_guess/predict.py`가 입력 복합체 PDB에서 특징을 만드는 방식이다.
이 구조를 모르면 입력 준비 실수를 진단할 수 없다.

| 특징 | 출처 | 비고 |
| --- | --- | --- |
| MSA | 없음 (단일 서열) | 설계 서열에는 동족체가 없으므로 MSA를 쓰지 않는다 |
| 템플릿 | **표적 잔기만** 전체 원자 좌표·마스크 | 결합체 잔기는 0으로 마스크되어 자유롭게 예측된다 |
| 초기 좌표 | 복합체 **전체**의 전체 원자 좌표 | `initial_guess`. 설계 좌표에서 출발하게 한다 |
| recycle | 기본 3회 | |
| 모델 | `model_1_ptm` | |

표적 템플릿은 주사슬뿐 아니라 **사이드체인 좌표까지 그대로 들어간다**. 따라서 입력 PDB의
표적 사이드체인이 실제 구조와 다르면 AF2가 잘못된 표적 표면을 보게 된다.
실제로 이 때문에 재현이 실패했다. [문제 기록](issues/2026-11-18-trka-target-sidechains.md)

## 지표 정의

| 지표 | 정의 | 산출 |
| --- | --- | --- |
| `pae_interaction` | 결합면 예측 정렬 오차. 사슬 간 PAE 블록 두 개의 평균 | 업스트림 코드 |
| `plddt_binder` | 결합체 구간 pLDDT 평균 | 업스트림 코드 |
| `binder_aligned_rmsd` | 결합체만 정렬했을 때의 RMSD. **접힘** 정확도 | 업스트림 코드 |
| `target_aligned_rmsd` | 표적을 정렬한 좌표계에서의 결합체 RMSD. **배치** 정확도 | 업스트림 코드 |
| `rmsd_vs_original_design` | 표적 고정 후 결합체 Cα RMSD, 원 설계 구조 기준 | [src/af2_filter/compare.py](../src/af2_filter/compare.py) |
| `rmsd_vs_published_af2` | 같은 계산, 공개 AF2 구조 기준 | 같음 |

`binder_aligned_rmsd`와 `target_aligned_rmsd`를 분리해 보는 것이 중요하다. 전자가 작고 후자가
크면 **접힘은 맞았고 배치가 틀렸다**는 뜻이다. TrkA_88 재현 실패가 정확히 이 형태였다
(0.594 Å 대 31.135 Å).

RMSD 계산은 반사를 허용하지 않는 Kabsch 중첩을 쓰고, 표적 Cα로 정렬 변환을 구한 뒤
그 변환을 결합체에 적용한다. 결합체를 따로 최적 정렬하지 않는다.

## 통과 기준

논문(Watson et al. 2023) Extended Data Fig. 8 설명에 그대로 적혀 있다.

> "In silico success is defined in line with current best practice:
> **AF2 pLDDT of the monomer > 80, AF2 interaction pAE < 10,
> AF2 r.m.s.d. monomer vs design < 1 Å.**"

| 지표 | 기준 | 대응하는 출력 |
| --- | --- | --- |
| AF2 interaction pAE | < 10 | `pae_interaction` |
| AF2 pLDDT (monomer) | > 80 | `plddt_binder` |
| AF2 r.m.s.d. monomer vs design | < 1 Å | `binder_aligned_rmsd` |

업스트림 저장소도 같은 지표를 지목한다 — *"`pae_interaction` is the score that
showed the most predictivity in the experiments performed in the paper."*

이 기준은 **후보를 줄이는 용도**다. 통과가 결합을 의미하지 않는다. 자세한 해석 범위는
[취지 문서](00-purpose.md)의 "무엇을 성공으로 보는가"에 있다.

이 저장소에서 직접 측정한 바로는, 이미 필터를 통과한 설계들 사이에서 `pae_interaction`이
실제 결합 여부를 가르지 못했다. 실험에서 결합하지 않은 설계 14개가 전부 통과했다.
**통과한 후보들의 순위를 이 지표로 매기지 않는다.** [교정 결과](02-filter-calibration.md)

반대쪽도 측정했다. 선별을 거치지 않은 직접 설계 40개는 **0개가 통과했다.** 즉 이 기준은
**선별 전 집단을 거르는 데는 작동하고, 선별 후 집단을 가르는 데는 작동하지 않는다.**
거절은 세 기준 중 `pae_interaction` 하나가 한다(0/40). 같은 40개에서 `plddt_binder`는
32개, 접힘 RMSD는 21개가 통과했다. [설계 실행 결과](03-design-run.md)

## 검증 지점

입력 준비 코드는 다음을 실행 중에 단정(assert)한다. 조용히 틀린 입력이 들어가는 것을 막는다.

- 준비된 복합체의 서열이 `결합체 + 표적` 순서와 정확히 일치하는지
- 사슬 1 경계가 결합체 길이와 같은지
- 서열 치환이 설계 주사슬 좌표를 바꾸지 않았는지 (허용 오차 0.002 Å)
- 공개 결합체 서열이 공개 AF2 구조의 사슬 중 하나와 일치하는지
- **표적 잔기에 사이드체인 원자가 존재하는지** (GLY 제외)

마지막 항목은 나중에 추가됐다. 그 검사가 없던 동안 표적 사이드체인이 통째로 비어 있어도
파이프라인이 정상 종료하며 틀린 숫자를 냈다.
[문제 기록](issues/2026-11-18-trka-target-sidechains.md)

### 실행 후 점검

단정으로 잡을 수 없는 것이 하나 더 있다. **생성된 백본이 지정한 hotspot에 실제로 붙었는가.**
엉뚱한 면에 붙어도 파이프라인은 정상 종료하고, 그 경우 채점 결과는 아무것도 뜻하지 않는다.
[check_interface.py](../src/rfd3_design/check_interface.py)가 백본별로 계면 잔기와 hotspot
최단 거리를 뽑는다.

RFdiffusion3 출력은 표적 사슬을 1부터 다시 번호 매기므로 사양의 hotspot 번호와 직접 비교할
수 없다. 이 도구는 표적 입력의 첫 잔기 번호를 기준으로 옮긴 뒤 **옮긴 자리의 잔기 이름이
사양과 같은지 교차 검증**한다. 번호를 잘못 옮긴 채 "접촉 없음"으로 결론 내는 것을 막는다.
