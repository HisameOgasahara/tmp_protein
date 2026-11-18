# 참고문서

## 논문

| 항목 | 내용 |
| --- | --- |
| 설계 방법·공개 데이터 출처 | RFdiffusion 논문, Nature 2023, [doi:10.1038/s41586-023-06415-8](https://doi.org/10.1038/s41586-023-06415-8) |
| AF2 initial guess 채점 절차 | `dl_binder_design` 저장소에 구현된 절차 (아래) |

재현 대상인 TrkA 결합체 설계는 RFdiffusion 논문의 공개 자료에 포함돼 있다.
채점에 쓰는 AF2 initial guess 절차는 `dl_binder_design` 저장소의 구현을 그대로 쓴다.

## 공개 데이터

| 항목 | 값 |
| --- | --- |
| 데이터셋 | [doi:10.6084/m9.figshare.22662094.v1](https://doi.org/10.6084/m9.figshare.22662094.v1) |
| 아카이브 | `https://ndownloader.figshare.com/files/40226533` |
| 아카이브 내 경로 | `PUBLIC_RELEASE/experimentally_tested/TrkA_binders/` |

현재 받아둔 파일은 [inputs/trka/](../inputs/trka/)에 있고 SHA-256은
[inputs/trka/provenance.json](../inputs/trka/provenance.json)에 기록돼 있다.

| 파일 | 내용 |
| --- | --- |
| `design.pdb` | RFdiffusion 출력 백본. **주사슬 전용** (N, CA, C, O) |
| `binder.fasta` | TrkA_88 결합체 서열 93잔기 |
| `published_af2.pdb` | 저자들의 AF2 예측 복합체 |
| `published_sequences.fasta` | 공개 설계 95개의 서열 |
| `published_results.csv` | 설계 95개의 조건과 **실험 결합 라벨** |

`published_results.csv`의 `Binder` 열이 실험 결과다. 95개 중 6개가 `True`이고
해당 설계는 10, 17, 23, 54, 73, 88번이다. 이 라벨이 채점기 교정의 정답지다.

## 표적 실험 구조

| 항목 | 값 |
| --- | --- |
| PDB | [1WWW](https://www.rcsb.org/structure/1WWW) 체인 X — NGF–TrkA 복합체의 TrkA 수용체 |
| 영역 | Ig 유사 D5 도메인, 잔기 282–382 (101잔기) |
| 다운로드 | `https://files.rcsb.org/download/1WWW.pdb` |
| 용도 | `design.pdb`에 없는 표적 사이드체인 공급 |

**서열이 `design.pdb` 표적 101잔기와 글자 하나까지 동일하다.** 그래서 잔기별 대응이
확정되고 정렬 모호성이 없다. SHA-256은
[inputs/trka/provenance.json](../inputs/trka/provenance.json)의
`target_sidechain_source`에 기록돼 있다.

### 확인된 주의사항

- 아카이브에서 현재 받아온 것은 **TrkA_88 한 건의 구조뿐**이다. 나머지 94개 설계의
  구조 파일은 아직 받지 않았다. 교정 작업에는 추가 다운로드가 필요하다.
- figshare 아카이브는 `RFdiffusion_designs.zip` 하나이고 **251.7 MB**다. 파일 목록은
  `https://api.figshare.com/v2/articles/22662094/files`로 확인된다.
  `curl -I`(HEAD)는 S3 서명 URL이 거부하므로 **GET으로 받아야 한다.** HEAD 응답의 403을
  다운로드 실패로 오해하지 말 것.
- 저자들이 RFdiffusion 입력으로 쓴 원본 표적 PDB는 아직 꺼내보지 않았다. 현재 사이드체인
  공급원은 1WWW이고, 아카이브의 원본 표적과 비교해볼 가치가 있다.
- 아카이브는 Colab에서 받는 것이 낫다. 로컬 디스크를 쓰지 않고, 어차피 AF2 실행이
  거기서 일어난다.
- `provenance.json`의 `published_pose_rmsd_angstrom: 1.4`는 CSV에 없는 값이며 수동으로
  입력됐다. 다만 공개 AF2 구조와 설계 구조로 직접 재계산한 값이 **1.3896 Å**로 일치하므로
  지표 정의 자체는 검증됐다.
- 표적은 TrkA의 Ig 유사 D5 도메인 101잔기이며, `design.pdb`에서 잔기 번호 94–194다.
  서열에 N-글리코실화 sequon이 포함되지만 AF2는 당사슬을 모델링하지 않는다.

## 고정한 업스트림 리비전

| 대상 | 리비전 |
| --- | --- |
| [nrbennet/dl_binder_design](https://github.com/nrbennet/dl_binder_design) | `cafa3853ac94dceb1b908c8d9e6954d71749871a` |
| RFdiffusion3 / MPNN 런타임 (foundry) | `0d0b0ba44fab7ca76aa4b625c014ce5964c7d284` |

## 모델 가중치

| 대상 | 출처 |
| --- | --- |
| AlphaFold2 `params_model_1_ptm` | `https://storage.googleapis.com/alphafold/alphafold_params_2022-12-06.tar` |

가중치 SHA-256은 진단 실행의 `source.json`에 기록된다.

## 읽을 때 유용한 업스트림 코드

| 파일 | 왜 |
| --- | --- |
| `af2_initial_guess/predict.py` | 특징 구성, 템플릿 마스킹, 점수 산출의 전체 흐름 |
| `af2_initial_guess/af2_util.py` | `af2_get_atom_positions`가 **모든 원자**를 템플릿에 넣는 지점 |
| `mpnn_fr/dl_interface_design.py` | ProteinMPNN + FastRelax 단계. 사이드체인 패킹이 여기서 일어난다 |

## 다른 표적 (현재 비활성)

PD-L1 (PDB 8AOM) 입력이 [inputs/pdl1_8aom/](../inputs/pdl1_8aom/)에 남아 있다.
RFdiffusion3 공식 예제의 hotspot 설정이다. 이 표적으로 돌린 과거 실행은 채점을
AF2 initial guess가 아닌 서열 전용 RF3 예측으로 했기 때문에 결과를 쓰지 않는다.
재평가하려면 교정된 AF2 필터를 적용해야 한다.
