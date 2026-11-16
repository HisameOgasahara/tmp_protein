import argparse
import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path
from statistics import mean
from urllib.request import Request, urlopen

import matplotlib.pyplot as plt
from openpyxl import load_workbook


PAPER = "https://pmc.ncbi.nlm.nih.gov/articles/PMC12852815/"
SUPPLEMENTS = "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC12852815/supplementaryFiles"
WORKBOOK = "41467_2025_67866_MOESM4_ESM.xlsx"
CANDIDATE = "PDGFRαbp-7LBF"


def write_csv(path, columns, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        writer.writerows(rows)


def extract_functional_sheets(output):
    request = Request(SUPPLEMENTS, headers={"User-Agent": "7LBF-education-Colab"})
    with urlopen(request, timeout=180) as response:
        archive_data = response.read()
    with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
        entries = [name for name in archive.namelist() if Path(name).name == WORKBOOK]
        if len(entries) != 1:
            raise ValueError(f"Expected one source workbook named {WORKBOOK}.")
        workbook_data = archive.read(entries[0])

    workbook = load_workbook(io.BytesIO(workbook_data), read_only=True, data_only=True)
    try:
        sheet = workbook["Figure5E"]
        raw_rows = list(sheet.iter_rows(max_row=24, max_col=5, values_only=True))
    finally:
        workbook.close()

    observations = []
    for marker, heading, start, end in (("p-ERK", 4, 5, 13), ("p-AKT", 15, 16, 24)):
        if raw_rows[heading - 1][1] != marker:
            raise ValueError(f"Unexpected Figure5E layout at row {heading}.")
        for cells in raw_rows[start - 1:end]:
            concentration = cells[1]
            for replicate, intensity in enumerate(cells[2:5], start=1):
                if isinstance(intensity, (int, float)):
                    observations.append((marker, concentration, replicate, intensity))

    write_csv(output / "Figure5E_measurements.csv",
              ("marker", "concentration_nM", "biological_replicate", "normalized_intensity"),
              observations)
    return hashlib.sha256(workbook_data).hexdigest(), observations


def plot_response(output, observations):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8), sharey=True, layout="constrained")
    for ax, marker, color in zip(axes, ("p-ERK", "p-AKT"), ("#15677b", "#335ca6")):
        responses = {}
        for endpoint, concentration, _, intensity in observations:
            if endpoint == marker:
                responses.setdefault(concentration, []).append(intensity)

        concentrations = sorted(responses)
        ax.plot(concentrations, [mean(responses[x]) for x in concentrations],
                color=color, linewidth=1.5, label="Mean of available measurements")
        for concentration, replicates in responses.items():
            ax.scatter([concentration] * len(replicates), replicates, color=color, s=18, alpha=0.65)
        ax.set_xscale("symlog", linthresh=0.01)
        ax.set(title=marker, xlabel="7LBF concentration (nM)")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("Normalized signal")
    fig.savefig(output / "7lbf_dose_response.png", dpi=170)
    plt.close(fig)


def plot_inhibition_summary(output):
    endpoints = ("ERK phosphorylation", "AKT phosphorylation")
    values = (19.6, 38.25)
    fig, ax = plt.subplots(figsize=(7, 3.3), layout="constrained")
    bars = ax.barh(endpoints, values, color=("#15677b", "#335ca6"))
    ax.invert_yaxis()
    ax.bar_label(bars, labels=[f"{value:g} nM" for value in values], padding=5)
    ax.set(xlabel="Reported IC50 (nM)", xlim=(0, 48), title=f"{CANDIDATE} | Cellular signalling")
    ax.spines[["top", "right"]].set_visible(False)
    fig.savefig(output / "7lbf_inhibition.png", dpi=170)
    plt.close(fig)


def build_report(output, version, commit):
    for folder in ("data", "figures", "provenance"):
        (output / folder).mkdir(parents=True, exist_ok=True)

    write_csv(output / "data" / "candidate_path.csv",
              ("candidate", "stage", "evidence", "paper_section"), [
                  (CANDIDATE, "Target", "Human PDGFRα; structural reference PDB 7LBF",
                   "Production scale computational protein design workflow"),
                  (CANDIDATE, "Design", "β-pairing-conditioned RFdiffusion and ProteinMPNN",
                   "Main text and Methods"),
                  (CANDIDATE, "Screen", "Yeast-display library of 5,427 designs for this target structure",
                   "Main text"),
                  (CANDIDATE, "Binding", "SPR; Kd 137 pM", "Figure 2 and main text"),
                  (CANDIDATE, "Cell response", "ERK and AKT phosphorylation inhibition", "Figure 5d–e"),
              ])
    write_csv(output / "data" / "reported_endpoints.csv",
              ("candidate", "assay", "endpoint", "value", "unit", "paper_section"), [
                  (CANDIDATE, "SPR", "Kd", 137, "pM", "Figure 2 and main text"),
                  (CANDIDATE, "Cell signalling", "ERK phosphorylation IC50", 19.6, "nM", "Figure 5d–e"),
                  (CANDIDATE, "Cell signalling", "AKT phosphorylation IC50", 38.25, "nM", "Figure 5d–e"),
              ])
    workbook_hash, observations = extract_functional_sheets(output / "data")
    plot_inhibition_summary(output / "figures")
    plot_response(output / "figures", observations)
    provenance = {
        "notebook_version": version,
        "script_commit": commit,
        "candidate": CANDIDATE,
        "paper": PAPER,
        "doi": "10.1038/s41467-025-67866-3",
        "supplement_archive": SUPPLEMENTS,
        "workbook_member": WORKBOOK,
        "workbook_sha256": workbook_hash,
        "extracted_sheets": ["Figure5E"],
        "endpoint_origin": "Reported values transcribed from the paper; no model output or curve refit.",
    }
    (output / "provenance" / "sources.json").write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    build_report(args.output, args.version, args.commit)
