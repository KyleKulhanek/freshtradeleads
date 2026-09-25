import csv
from freshtradeleads.importer import import_xlsx
from freshtradeleads.inventory import build_inventory


def test_inventory_matrix_generation(engine,workbook,tmp_path):
    import_xlsx(engine,workbook)
    result=build_inventory(engine,tmp_path/"data",tmp_path/"docs",generate_packs=False)
    with open(result["matrix_path"],newline="",encoding="utf-8") as handle: rows=list(csv.DictReader(handle))
    assert rows and {"clear_percent","phone_percent","bond_information_count","candidate_score"}.issubset(rows[0])
    assert (tmp_path/"docs"/"inventory-analysis.md").exists()

