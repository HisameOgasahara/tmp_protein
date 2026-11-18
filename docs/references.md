# 참고문서

## 논문

| 항목 | 내용 |
| --- | --- |
| 설계 방법·공개 데이터 출처 | RFdiffusion 논문, Nature 2023, [doi:10.1038/s41586-023-06415-8](https://doi.org/10.1038/s41586-023-06415-8) |
| 전문 (봇 차단 없이 읽히는 경로) | `https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10468394/fullTextXML` |
| AF2 initial guess 채점 절차 | `dl_binder_design` 저장소에 구현된 절차 (아래) |

PMC 웹페이지와 bioRxiv는 자동 요청을 차단하거나 제한. Europe PMC의 전문 XML API는 통과.

### 이 저장소가 논문에서 직접 인용하는 값

| 값 | 원문 |
| --- | --- |
| 통과 기준 | "In silico success is defined in line with current best practice: AF2 pLDDT of the monomer > 80, AF2 interaction pAE < 10, AF2 r.m.s.d. monomer vs design < 1 Å." |
| 선별에 AF2가 쓰였음 | "We attribute one order of magnitude to RFdiffusion, and the second to filtering with AF2" |
| TrkA_88의 보고값 | "Binders: ... TrkA_88 (1.4 Å)" — AF2 예측과 설계의 RMSD |
| 다섯 표적 전체 실험 성공률 | "The overall experimental success rate ... was 19%" |

마지막 값은 다섯 표적 합산. TrkA 단독은 공개 CSV 기준 6/95 = 6.3%.

## 공개 데이터

| 항목 | 값 |
| --- | --- |
| 데이터셋 | [doi:10.6084/m9.figshare.22662094.v1](https://doi.org/10.6084/m9.figshare.22662094.v1) |
| 아카이브 | `https://ndownloader.figshare.com/files/40226533` |
| 아카이브 내 경로 | `PUBLIC_RELEASE/experimentally_tested/TrkA_binders/` |

저장된 파일은 [inputs/trka/](../inputs/trka/), SHA-256은
[provenance.json](../inputs/trka/provenance.json).

| 파일 | 내용 |
| --- | --- |
| `design.pdb` | RFdiffusion 출력 백본. **주사슬 전용** (N, CA, C, O) |
| `binder.fasta` | TrkA_88 결합체 서열 93잔기 |
| `published_af2.pdb` | 저자들의 AF2 예측 복합체 |
| `published_sequences.fasta` | 공개 설계 95개의 서열 |
| `published_results.csv` | 설계 95개의 조건과 **실험 결합 라벨** |

`published_results.csv`의 `Binder` 열이 실험 결과. 95개 중 6개가 `True` — 설계 10, 17,
23, 54, 73, 88번.

## 표적 실험 구조

| 항목 | 값 |
| --- | --- |
| PDB | [1WWW](https://www.rcsb.org/structure/1WWW) 체인 X — NGF–TrkA 복합체의 TrkA 수용체 |
| 영역 | Ig 유사 D5 도메인, 잔기 282–382 (101잔기) |
| 다운로드 | `https://files.rcsb.org/download/1WWW.pdb` |
| 용도 | `design.pdb`에 없는 표적 사이드체인 공급 |

서열이 `design.pdb` 표적 101잔기와 완전히 동일 — 잔기별 대응이 확정되고 정렬 모호성 없음.
SHA-256은 [provenance.json](../inputs/trka/provenance.json)의 `target_sidechain_source`.

### 취급 주의

| 항목 | 내용 |
| --- | --- |
| 아카이브 크기 | `RFdiffusion_designs.zip` 하나, 251.7 MB. 목록은 `https://api.figshare.com/v2/articles/22662094/files` |
| 다운로드 방식 | GET만 가능. S3 서명 URL이 HEAD를 거부하므로 `curl -I`의 403은 실패가 아님 |
| 받는 위치 | Colab. 로컬 디스크를 쓰지 않고 AF2 실행도 거기서 일어남 |
| `published_pose_rmsd_angstrom: 1.4` | CSV에 없는 수동 입력값. 공개 AF2 구조와 설계 구조로 재계산하면 1.3896 Å로 일치 |
| 표적 번호 | `design.pdb`에서 94–194. 서열에 N-글리코실화 sequon이 있으나 AF2는 당사슬을 모델링하지 않음 |

## 고정한 업스트림 리비전

| 대상 | 리비전 |
| --- | --- |
| [nrbennet/dl_binder_design](https://github.com/nrbennet/dl_binder_design) | `cafa3853ac94dceb1b908c8d9e6954d71749871a` |
| RFdiffusion3 / MPNN 런타임 (foundry) | `0d0b0ba44fab7ca76aa4b625c014ce5964c7d284` |

## 모델 가중치

| 대상 | 출처 |
| --- | --- |
| AlphaFold2 `params_model_1_ptm` | `https://storage.googleapis.com/alphafold/alphafold_params_2022-12-06.tar` |

가중치 SHA-256은 진단 실행의 `source.json`에 기록.

## 읽을 때 유용한 업스트림 코드

| 파일 | 왜 |
| --- | --- |
| `af2_initial_guess/predict.py` | 특징 구성, 템플릿 마스킹, 점수 산출의 전체 흐름 |
| `af2_initial_guess/af2_util.py` | `af2_get_atom_positions`가 **모든 원자**를 템플릿에 넣는 지점 |
| `mpnn_fr/dl_interface_design.py` | ProteinMPNN + FastRelax 단계. 사이드체인 패킹 지점 |
