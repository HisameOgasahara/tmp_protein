def rank_docking_candidates(rows, clash_distance):
    """Rank eligible poses in their original MEGADOCK score order."""
    ranked = {}
    selected_rank = None
    eligible_count = 0
    for row in sorted(rows, key=lambda row: int(row["rank"])):
        rank = int(row["rank"])
        distance = float(row["min_interchain_heavy_atom_distance_angstrom"])
        if distance < clash_distance:
            ranked[rank] = {
                "filtered_rank": None,
                "selection_exclusion_reason": "heavy_atom_clash",
                "selected": False,
            }
            continue
        eligible_count += 1
        if selected_rank is None:
            selected_rank = rank
        ranked[rank] = {
            "filtered_rank": eligible_count,
            "selection_exclusion_reason": None,
            "selected": rank == selected_rank,
        }
    return ranked, {
        "eligible_poses": eligible_count,
        "selected_original_rank": selected_rank,
        "status": "selected" if selected_rank is not None else "no_eligible_poses",
    }
