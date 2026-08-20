"""
Unit Test Script for Product Enrichment Agent Modules
"""

from pd_enrichment.detector import detect_columns
from pd_enrichment.normalizer import normalize_attribute_value
from pd_enrichment.exporter import export_enrichment_results
import pandas as pd

def test_detector():
    cols = ["SKU ID", "Product Name", "Brand", "Category", "MFG Part #", "Product Width", "Product Weight", "Voltage", "Operating Temp"]
    res = detect_columns(cols)
    assert "SKU ID" in res["identity_columns"], "SKU ID should be identity"
    assert "Product Name" in res["identity_columns"], "Product Name should be identity"
    assert "Product Width" in res["attribute_columns"], "Product Width should be attribute"
    assert "Product Weight" in res["attribute_columns"], "Product Weight should be attribute"
    assert "Voltage" in res["attribute_columns"], "Voltage should be attribute"
    assert res["primary_search_column"] == "MFG Part #", "Primary search column should be MFG Part #"
    print("[PASS] Detector tests passed!")

def test_normalizer():
    assert normalize_attribute_value("12.5 inches")["normalized_value"] == "12.5 in"
    assert normalize_attribute_value("20 pounds")["normalized_value"] == "20 lb"
    assert normalize_attribute_value("220 VAC")["normalized_value"] == "220 V AC"
    assert normalize_attribute_value("100 watts")["normalized_value"] == "100 W"
    assert normalize_attribute_value("Red / Black")["normalized_value"] == "Red / Black"
    assert normalize_attribute_value(None)["normalized_value"] == ""
    print("[PASS] Normalizer tests passed!")

def test_pydantic_schema():
    from pd_enrichment.schemas import EnrichedAttributeItem
    
    # Test unit standardization
    item1 = EnrichedAttributeItem(value="2.64 inches", unit="inches", confidence=95)
    assert item1.unit == "in", "Unit 'inches' should normalize to 'in'"
    
    item2 = EnrichedAttributeItem(value="0.61 lbs", unit="lbs", confidence=88)
    assert item2.unit == "lb", "Unit 'lbs' should normalize to 'lb'"
    
    item3 = EnrichedAttributeItem(value="120 volts", unit="volts", confidence=90)
    assert item3.unit == "V", "Unit 'volts' should normalize to 'V'"
    
    print("[PASS] Pydantic Schema & Normalization tests passed!")

if __name__ == "__main__":
    test_detector()
    test_normalizer()
    test_pydantic_schema()
    print("\nALL UNIT TESTS PASSED SUCCESSFULLY!")

