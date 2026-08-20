"""
Column Detection Module
Classifies input dataframe columns into Core Identity Columns vs Enrichable Attribute Columns.
"""

import re
from typing import Dict, List, Tuple

# Keywords that explicitly indicate an attribute even if preceded by "Product " or "Item "
ATTRIBUTE_KEYWORDS = {
    "width", "height", "length", "depth", "weight", "voltage", "wattage", 
    "color", "colour", "material", "temp", "temperature", "dimension", "dimensions",
    "size", "capacity", "power", "amperage", "amps", "volts", "watts", "pressure",
    "speed", "rpm", "frequency", "flow rate", "warranty", "description", "overview",
    "spec", "specification", "specifications", "finish", "type", "mounting", "flow",
    "diameter", "thickness", "current", "connector", "port", "battery", "package",
    "operating temp", "operating temperature", "noise", "output", "input"
}

# Core identity terms
IDENTITY_KEYWORDS = {
    "sku", "sku id", "sku_id", "part #", "mfg part #", "mfg part number", "part number",
    "mpn", "upc", "gtin", "ean", "item #", "item number", "product id", "product_id",
    "model #", "model number", "model", "product name", "item name", "title",
    "brand", "manufacturer", "mfr", "mfr name", "category", "subcategory", "class"
}


def is_attribute_column(col_name: str) -> bool:
    """Checks if a column name represents a product attribute."""
    clean_name = col_name.strip().lower()
    
    # Exception: Product Name or Item Name is an Identity column, NOT an attribute
    if clean_name in ["product name", "item name", "title", "product title", "item title"]:
        return False

    # Check if any attribute keyword matches as a standalone word or token
    tokens = set(re.split(r'[\s_\-\/\\]+', clean_name))
    if tokens.intersection(ATTRIBUTE_KEYWORDS):
        return True
        
    for kw in ATTRIBUTE_KEYWORDS:
        if kw in clean_name and len(kw) > 3:
            return True
            
    return False


def detect_columns(columns: List[str], preferred_search_col: str = None) -> Dict[str, any]:
    """
    Analyzes column names from file header and categorizes them into:
      - identity_columns
      - attribute_columns
      - primary_search_column
    """
    identity_cols = []
    attribute_cols = []
    
    for col in columns:
        clean = col.strip().lower()
        
        # Explicit check: If it has attribute keywords (and not product name), it's an attribute
        if is_attribute_column(col):
            attribute_cols.append(col)
            continue
            
        # Check if it matches identity keywords
        is_ident = False
        tokens = set(re.split(r'[\s_\-\/\\]+', clean))
        if tokens.intersection(IDENTITY_KEYWORDS) or any(kw in clean for kw in ["sku", "part #", "mpn", "upc", "brand", "model", "product name", "item name"]):
            is_ident = True
            
        if is_ident:
            identity_cols.append(col)
        else:
            attribute_cols.append(col)
            
    # Determine best search column
    search_col = None
    if preferred_search_col and preferred_search_col in columns:
        search_col = preferred_search_col
    else:
        # Search priority: MFG Part # / MPN > SKU > Product Name > Model > Brand
        priority_terms = ["mfg part", "mpn", "part #", "part number", "sku", "product name", "item name", "model", "title"]
        for term in priority_terms:
            for col in identity_cols:
                if term in col.lower():
                    search_col = col
                    break
            if search_col:
                break
                
        if not search_col:
            search_col = identity_cols[0] if identity_cols else columns[0]
            
    return {
        "identity_columns": identity_cols,
        "attribute_columns": attribute_cols,
        "primary_search_column": search_col
    }
