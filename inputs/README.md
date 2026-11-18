# 입력

실행 간에 바뀌지 않는 고정 입력이다. 출처와 SHA-256은
[참고문서](../docs/references.md)에 기록한다.

| 폴더 | 내용 |
| --- | --- |
| [trka/](trka/) | TrkA 결합체 공개 설계 자료. 재현·교정의 기준 |
| [pdl1_8aom/](pdl1_8aom/) | PD-L1 (PDB 8AOM) 설계 입력. 현재 비활성 |

## trka

| 파일 | 내용 |
| --- | --- |
| `design.pdb` | RFdiffusion 출력 백본. 결합체 93잔기 + 표적 101잔기 |
| `binder.fasta` | TrkA_88 결합체 서열 |
| `published_af2.pdb` | 저자들의 AF2 예측 복합체 |
| `published_sequences.fasta` | 공개 설계 95개 서열 |
| `published_results.csv` | 설계 95개의 조건과 실험 결합 라벨 |
| `provenance.json` | 출처 URL과 SHA-256 |

**`design.pdb`는 주사슬 전용이다.** N, CA, C, O만 있고 사이드체인이 없다. 결합체 93잔기는
전부 GLY 플레이스홀더이며, 실제 서열은 `binder.fasta`에서 가져와 입히는 것이 정상 절차다.
표적 사이드체인이 없는 것이 재현 실패의 원인이었다 —
[문제 기록](../docs/issues/2026-11-18-trka-target-sidechains.md).

`published_results.csv`의 `Binder` 열이 실험 결과다. 95개 중 6개가 결합체(설계 10, 17, 23,
54, 73, 88번)다. 이 라벨이 채점기 교정의 정답지다.

현재 구조 파일은 TrkA_88 한 건만 받아져 있다. 교정 작업에는 나머지 설계의 구조를
아카이브에서 추가로 받아야 한다.

## pdl1_8aom

RFdiffusion3 공식 예제의 입력이다. `pdl1.json`에 contig, hotspot 잔기, 수소결합 공여자
지정이 들어 있고 `pdl1_cropped.pdb`가 표적 구조(114잔기)다.
