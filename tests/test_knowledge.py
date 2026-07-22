import json
from pathlib import Path


def test_all_knowledge_json_is_valid():
    root = Path(__file__).resolve().parents[1] / "knowledge"
    files = list(root.rglob("*.json"))
    assert files
    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path


def test_catalog_and_core_categories_exist():
    root = Path(__file__).resolve().parents[1] / "knowledge"
    assert (root / "catalog.json").exists()
    for folder in [
        "01_market_structure", "02_support_resistance", "03_candlesticks",
        "04_fvg", "05_order_blocks", "06_liquidity", "07_scenarios",
        "08_indicators", "09_rules", "10_reference_images"
    ]:
        assert (root / folder).is_dir(), folder
