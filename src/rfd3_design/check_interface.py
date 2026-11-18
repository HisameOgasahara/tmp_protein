"""생성된 백본이 의도한 에피토프에 붙었는지 확인한다.

RFdiffusion3 출력은 표적 사슬을 1부터 다시 번호 매긴다. 사양의 hotspot 번호
(`design_spec.json`의 `B108` 등)와 직접 비교할 수 없으므로, 표적 입력의 첫 잔기
번호를 기준으로 옮긴 뒤 비교한다. 잔기 이름까지 함께 확인해 옮긴 번호가
맞는지 교차 검증한다.

    python check_interface.py <backbone.pdb> [...] --spec <design_spec.json> --target <target.pdb>
"""

import argparse
import json
import math
import pathlib
import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VERSION = "0.1.0"
CUTOFF = 5.0


def read_atoms(path):
    """사슬별 (잔기번호, 잔기이름, 원자이름, 좌표) 목록. 수소는 제외한다."""
    chains = defaultdict(list)
    for line in pathlib.Path(path).read_text().splitlines():
        if not line.startswith("ATOM"):
            continue
        name = line[12:16].strip()
        if name.startswith("H") or line[76:78].strip() == "H":
            continue
        chains[line[21]].append(
            (
                int(line[22:26]),
                line[17:20].strip(),
                name,
                (float(line[30:38]), float(line[38:46]), float(line[46:54])),
            )
        )
    return chains


def first_residue(path, chain):
    atoms = read_atoms(path)[chain]
    if not atoms:
        raise ValueError(f"{path}에 사슬 {chain}이 없다")
    return min(number for number, _, _, _ in atoms)


def spec_hotspots(spec_path):
    """{잔기번호: 원자이름 집합} — 사양에 적힌 원래 번호 기준."""
    specification = json.loads(pathlib.Path(spec_path).read_text())
    (entry,) = specification.values()
    hotspots = {}
    for key, atoms in entry["select_hotspots"].items():
        hotspots[int(key[1:])] = {name.strip() for name in atoms.split(",")}
    return hotspots


def interface(chains, binder_chain, target_chain, cutoff=CUTOFF):
    """접촉 잔기 집합과 최단 거리."""
    binder = chains[binder_chain]
    target = chains[target_chain]
    touched_binder = set()
    touched_target = set()
    shortest = math.inf
    closest = {}
    for _, _, _, left in binder:
        for number, residue, _, right in target:
            distance = math.dist(left, right)
            shortest = min(shortest, distance)
            if number not in closest or distance < closest[number][0]:
                closest[number] = (distance, residue)
            if distance < cutoff:
                touched_target.add(number)
    for number, _, _, left in binder:
        for _, _, _, right in target:
            if math.dist(left, right) < cutoff:
                touched_binder.add(number)
                break
    return touched_binder, touched_target, shortest, closest


def check(path, offset, hotspots, binder_chain="A", target_chain="B"):
    chains = read_atoms(path)
    names = {number: residue for number, residue, _, _ in chains[target_chain]}
    touched_binder, touched_target, shortest, closest = interface(
        chains, binder_chain, target_chain
    )
    report = {
        "file": pathlib.Path(path).name,
        "binder_residues": len({n for n, _, _, _ in chains[binder_chain]}),
        "target_residues": len(names),
        "shortest_contact": round(shortest, 2),
        "interface_binder": len(touched_binder),
        "interface_target": len(touched_target),
        "hotspots": {},
    }
    for original in sorted(hotspots):
        shifted = original + offset
        distance, residue = closest.get(shifted, (math.inf, None))
        report["hotspots"][f"B{original}"] = {
            "shifted_to": shifted,
            "residue": residue or names.get(shifted),
            "closest": None if math.isinf(distance) else round(distance, 2),
            "contacted": shifted in touched_target,
        }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backbones", nargs="+")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--target-chain", default="B")
    parser.add_argument("--binder-chain", default="A")
    arguments = parser.parse_args()

    hotspots = spec_hotspots(arguments.spec)
    source_first = first_residue(arguments.target, arguments.target_chain)
    output_first = first_residue(arguments.backbones[0], arguments.target_chain)
    offset = output_first - source_first

    reports = [
        check(path, offset, hotspots, arguments.binder_chain, arguments.target_chain)
        for path in arguments.backbones
    ]

    print(f"check_interface {VERSION}  접촉 기준 {CUTOFF} Å (중원자)")
    print(
        f"표적 번호 이동: 입력 {source_first} -> 출력 {output_first} "
        f"(offset {offset:+d})"
    )
    labels = sorted(hotspots)
    header = "".join(f"  B{label}" for label in labels)
    print(f"{'백본':<16}{'결합여':>6}{'최단':>7}{'계면':>10}{header}")
    for report in reports:
        marks = ""
        for label in labels:
            entry = report["hotspots"][f"B{label}"]
            flag = "O" if entry["contacted"] else "-"
            marks += f"  {flag}{entry['closest']:5.2f}"
        print(
            f"{report['file']:<16}{report['binder_residues']:>6}"
            f"{report['shortest_contact']:>7.2f}"
            f"{report['interface_binder']:>5}/{report['interface_target']:<5}{marks}"
        )
    identities = {
        f"B{label}": {report["hotspots"][f"B{label}"]["residue"] for report in reports}
        for label in labels
    }
    print("\nhotspot 잔기 이름(이동 후):", json.dumps(identities, default=list))
    touched = {
        f"B{label}": sum(
            1 for report in reports if report["hotspots"][f"B{label}"]["contacted"]
        )
        for label in labels
    }
    print(f"hotspot 접촉 백본 수 / {len(reports)}:", json.dumps(touched))


if __name__ == "__main__":
    main()
