# 입력

실행 간에 바뀌지 않는 고정 입력. 출처와 SHA-256은 [references](../docs/references.md).

| 폴더 | 내용 |
| --- | --- |
| [trka/](trka/) | TrkA 결합체 공개 설계 자료. 재현·교정의 기준 |

## trka

| 파일 | 내용 |
| --- | --- |
| `design.pdb` | RFdiffusion 출력 백본. 결합체 93잔기 + 표적 101잔기 |
| `binder.fasta` | TrkA_88 결합체 서열 |
| `published_af2.pdb` | 저자들의 AF2 예측 복합체 |
| `published_sequences.fasta` | 공개 설계 95개 서열 |
| `published_results.csv` | 설계 95개의 조건과 실험 결합 라벨 |
| `target_1www_chainX.pdb` | PDB 1WWW 체인 X. 표적 사이드체인 공급원 |
| `design_spec.json` | 새 설계를 위한 RFdiffusion3 입력 사양 (contig, hotspot) |
| `provenance.json` | 출처 URL과 SHA-256 |

### design.pdb는 주사슬 전용

N, CA, C, O만 존재. 결합체 93잔기는 전부 GLY 플레이스홀더이고 실제 서열은
`binder.fasta`에서 가져와 입히는 것이 정상 절차.

표적 사이드체인 부재가 재현 실패의 원인
([문제 기록](../docs/issues/2026-11-18-trka-target-sidechains.md)).

### target_1www_chainX.pdb

TrkA Ig 유사 D5 도메인(잔기 282–382). 서열이 `design.pdb`의 표적 101잔기와 완전히 동일.
1차 altloc만 남기고 물 분자 제거.

파이프라인이 실행 중에 이 파일의 사이드체인을 설계 주사슬에 잔기별로 이식
([target_sidechains.py](../src/af2_filter/target_sidechains.py)). 이 표적은 공개 설계
95개가 공유.

### published_results.csv

`Binder` 열이 실험 결과. 95개 중 6개가 결합체(설계 10, 17, 23, 54, 73, 88번). 채점기
교정의 정답지.

구조 파일은 TrkA_88 한 건만 저장. 나머지 설계 구조는 노트북 02가 실행 중에 공개
아카이브에서 받아 사용.

### design_spec.json

hotspot은 공개 결합여 TrkA_88이 가장 깊이 파고든 소수성 잔기 셋 — B108 MET(최단 3.21 Å),
B115 PHE(3.80 Å), B145 LEU(3.15 Å). 계면 26잔기 중에서 선택.

설계용 표적 PDB는 실행 중에 `design.pdb`와 `target_1www_chainX.pdb`로부터 생성되므로 따로
두지 않음.

`contig`의 결합여 길이는 `70-95`지만 실행 코드가 이 범위를 고정 길이 몇 개로 좁힘
([trka_design.py](../src/rfd3_design/trka_design.py)의 `BINDER_LENGTHS`). 길이가 바뀌면
AF2 채점에서 JAX가 재컴파일하기 때문(길이당 92초). 이 파일은 에피토프와 허용 범위를,
코드는 실제로 뽑을 길이와 개수를 정함.
