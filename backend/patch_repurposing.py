"""
Patches /app/app/services/repurposing.py to replace the hand-rolled graph
conversion with nx_to_heterodata() — identical to what run_training.py uses.

Run inside the api container:
    python patch_repurposing.py
"""
import re, sys

TARGET = "/app/app/services/repurposing.py"

with open(TARGET, "r") as f:
    src = f.read()

# ── 1. Add import for nx_to_heterodata ───────────────────────────────────────
IMPORT_MARKER = "from app.ml.models.hgt import NeuroDrugHGT"
NEW_IMPORT = (
    "from app.ml.models.hgt import NeuroDrugHGT\n"
    "from app.ml.graph_convert import nx_to_heterodata"
)
if "from app.ml.graph_convert import nx_to_heterodata" not in src:
    src = src.replace(IMPORT_MARKER, NEW_IMPORT, 1)
    print("✅  Added nx_to_heterodata import")
else:
    print("⏭   nx_to_heterodata import already present")

# ── 2. Replace the graph conversion block ────────────────────────────────────
# We anchor on two unique strings that bracket the old hand-rolled section.
# START: just after the build_from_database() call
# END:   just before the drug_names_needed query

START_ANCHOR = re.compile(
    r"(nx_graph\s*=\s*await builder\.build_from_database\([^)]*\)[^\n]*\n)",
    re.MULTILINE,
)

END_ANCHOR = "drug_names_needed = [r[\"drug_name\"] for r in results]"

if END_ANCHOR not in src:
    # Try alternate form
    END_ANCHOR = "drug_names_needed = [r['drug_name'] for r in results]"

if END_ANCHOR not in src:
    print("❌  Could not find END_ANCHOR — aborting.")
    sys.exit(1)

m = START_ANCHOR.search(src)
if not m:
    print("❌  Could not find START_ANCHOR — aborting.")
    sys.exit(1)

# Everything from after the build_from_database line up to (not including)
# drug_names_needed gets replaced.
old_section_start = m.end()
old_section_end   = src.index(END_ANCHOR)

old_section = src[old_section_start:old_section_end]
print(f"📋  Old section is {len(old_section.splitlines())} lines "
      f"(chars {old_section_start}–{old_section_end})")

NEW_SECTION = '''
        # ── Convert graph (identical pipeline to run_training.py) ─────────
        # nx_to_heterodata adds reverse edges and uses the same feature
        # functions as training, guaranteeing that metadata() matches the
        # checkpoint and every weight in k_rel / v_rel loads without
        # shape mismatches.
        hetero_data, node_lists = nx_to_heterodata(nx_graph)

        drug_list    = node_lists.get("Drug", [])
        disease_list = node_lists.get("Disease", [])
        n_drug       = len(drug_list)
        drug_names   = [nx_graph.nodes[k].get("name", k) for k in drug_list]

        disease_key = f"Disease:{disease.efo_id}"
        if disease_key not in disease_list:
            raise ValueError(
                f"Disease node '{disease_key}' not found in graph. "
                "Ensure ETL has been run for this disease."
            )
        disease_idx = disease_list.index(disease_key)

        # ── Initialise model with same metadata as training ───────────────
        model = NeuroDrugHGT(
            metadata=hetero_data.metadata(),
            hidden_channels=128,
            num_layers=2,
            num_heads=4,
        )
        predictor = DrugRepurposingPredictor(model)
        predictor.load_checkpoint(model_version.checkpoint_path)

        drug_nodes    = torch.arange(n_drug)
        disease_nodes = torch.tensor([disease_idx])

        x_dict          = {k: hetero_data[k].x          for k in hetero_data.node_types}
        edge_index_dict = {k: hetero_data[k].edge_index for k in hetero_data.edge_types}

        results = predictor.rank_candidates(
            x_dict,
            edge_index_dict,
            drug_nodes,
            disease_nodes,
            drug_names,
            disease.name,
            top_k=top_k,
        )

        '''

src = src[:old_section_start] + NEW_SECTION + src[old_section_end:]

# ── 3. Fix num_layers if still 3 ─────────────────────────────────────────────
src = src.replace(
    "hidden_channels=128, num_layers=3, num_heads=4",
    "hidden_channels=128, num_layers=2, num_heads=4",
)

with open(TARGET, "w") as f:
    f.write(src)

print("✅  repurposing.py patched successfully.")
print("    API will hot-reload within a few seconds.")
