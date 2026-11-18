# 입력

실행 간에 바뀌지 않는 고정 입력이다. 출처와 SHA-256은
[참고문서](../docs/references.md)에 기록한다.

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

**`design.pdb`는 주사슬 전용이다.** N, CA, C, O만 있고 사이드체인이 없다. 결합체 93잔기는
전부 GLY 플레이스홀더이며, 실제 서열은 `binder.fasta`에서 가져와 입히는 것이 정상 절차다.
표적 사이드체인이 없는 것이 재현 실패의 원인이었다 —
[문제 기록](../docs/issues/2026-11-18-trka-target-sidechains.md).

`target_1www_chainX.pdb`가 그 보완용이다. TrkA Ig 유사 D5 도메인(잔기 282–382)이고
**서열이 `design.pdb` 표적 101잔기와 완전히 동일**하다. 1차 altloc만 남기고 물 분자는
제거했다. 파이프라인이 실행 중에 이 파일의 사이드체인을 설계 주사슬에 잔기별로 이식한다
([src/af2_filter/target_sidechains.py](../src/af2_filter/target_sidechains.py)).
이 표적은 공개 설계 95개가 모두 공유하므로 한 번 복원하면 전부에 쓰인다.

`published_results.csv`의 `Binder` 열이 실험 결과다. 95개 중 6개가 결합체(설계 10, 17, 23,
54, 73, 88번)다. 이 라벨이 채점기 교정의 정답지다.

현재 구조 파일은 TrkA_88 한 건만 받아져 있다. 교정 작업에는 나머지 설계의 구조를
아카이브에서 추가로 받아야 한다.

`design_spec.json`의 hotspot은 공개 결합여 TrkA_88이 실제로 가장 깊이 파고든 소수성 잔기
셋이다 — B108 MET(최단 3.21 Å), B115 PHE(3.80 Å), B145 LEU(3.15 Å). 계면 26잔기 중에서
고른 것이고, 임의의 표면이 아니라 결합이 확인된 에피토프를 겨냥한다. 설계용 표적 PDB는
실행 중에 `design.pdb`와 `target_1www_chainX.pdb`로부터 만들어지므로 따로 두지 않는다.

`contig`의 결합여 길이는 `70-95`로 적혀 있지만 **실행 코드가 이 범위를 몇 개의 고정
길이로 좁힌다** ([trka_design.py](../src/rfd3_design/trka_design.py)의 `BINDER_LENGTHS`).
길이가 바뀌면 AF2 채점에서 JAX가 매번 재컴파일하기 때문이다(길이당 92초).
이 파일은 에피토프와 허용 범위를, 코드는 실제로 뽑을 길이와 개수를 정한다.
