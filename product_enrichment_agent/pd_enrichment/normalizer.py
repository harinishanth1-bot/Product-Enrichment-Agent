"""
Attribute Normalizer & Unit Standardizer Module
Normalizes attribute values, preserves explicit units, and standardizes unit representations across both pre-existing and newly enriched values.
"""

import re
from typing import Dict, Any, Tuple, Optional

# Comprehensive standard unit mapping dictionary
UNIT_MAPPINGS = {
    # Length / Dimensions
    "inch": "in", "inches": "in", "in.": "in", "in": "in", '"': "in",
    "foot": "ft", "feet": "ft", "ft.": "ft", "ft": "ft", "'": "ft",
    "centimeter": "cm", "centimeters": "cm", "cm.": "cm", "cm": "cm",
    "millimeter": "mm", "millimeters": "mm", "mm.": "mm", "mm": "mm",
    "meter": "m", "meters": "m", "m.": "m", "m": "m",
    
    # Weight
    "pound": "lb", "pounds": "lb", "lbs": "lb", "lbs.": "lb", "lb.": "lb", "lb": "lb",
    "ounce": "oz", "ounces": "oz", "oz.": "oz", "oz": "oz",
    "kilogram": "kg", "kilograms": "kg", "kgs": "kg", "kg.": "kg", "kg": "kg",
    "gram": "g", "grams": "g", "g.": "g", "g": "g",
    
    # Electrical
    "volt": "V", "volts": "V", "v.": "V", "v": "V", "vac": "V AC", "vdc": "V DC",
    "watt": "W", "watts": "W", "w.": "W", "w": "W", "wattage": "W",
    "amp": "A", "amps": "A", "ampere": "A", "amperes": "A", "a.": "A", "a": "A",
    "hertz": "Hz", "hz.": "Hz", "hz": "Hz",
    
    # Temperature
    "deg f": "°F", "degree f": "°F", "degrees f": "°F", "fahrenheit": "°F", "f": "°F", "°f": "°F", "degf": "°F",
    "deg c": "°C", "degree c": "°C", "degrees c": "°C", "celsius": "°C", "c": "°C", "°c": "°C", "degc": "°C",
    "kelvin": "K", "k": "K",
    
    # Pressure / Speed / Power / Volume
    "psi": "PSI", "bar": "bar", "hp": "HP", "horsepower": "HP", "rpm": "RPM",
    "gallon": "gal", "gallons": "gal", "gal": "gal", "liter": "L", "liters": "L", "l": "L"
}


def normalize_attribute_value(val: Any, fallback_unit: Optional[str] = None) -> Dict[str, Any]:
    """
    Standardizes raw attribute value (both pre-existing and enriched) and extracts normalized value + unit.
    Returns:
      {
        "normalized_value": "70 °F",
        "raw_value": "70 F",
        "unit": "°F",
        "clean_num": 70.0
      }
    """
    if val is None or str(val).strip() == "" or str(val).strip().lower() in ["nan", "null", "none", "n/a", "na"]:
        return {
            "normalized_value": "",
            "raw_value": "" if val is None else str(val),
            "unit": None,
            "clean_num": None
        }

    raw_str = str(val).strip()
    clean_str = raw_str.strip('"`\'\t\r\n ')

    # Special handling for temperature formats like '70 F', '70 Deg F', '70F', '20 C'
    temp_match = re.match(
        r'^([+-]?\d+(?:\.\d+)?)\s*(?:°|deg|degree|degrees)?\s*([fcFC])\b', 
        clean_str, 
        re.IGNORECASE
    )
    if temp_match:
        num_part = temp_match.group(1)
        deg_part = temp_match.group(2).upper()
        unit_std = f"°{deg_part}"
        try:
            clean_num = float(num_part)
            num_formatted = f"{clean_num:g}"
        except ValueError:
            clean_num = None
            num_formatted = num_part

        return {
            "normalized_value": f"{num_formatted} {unit_std}",
            "raw_value": raw_str,
            "unit": unit_std,
            "clean_num": clean_num
        }

    # General Regex to capture numeric value and unit suffix
    num_unit_match = re.match(
        r'^([+-]?\d+(?:\.\d+)?)\s*([a-zA-Z°\'"]+(?:\s*[a-zA-Z°]+)?)?$', 
        clean_str
    )

    if num_unit_match:
        num_part = num_unit_match.group(1)
        unit_part = num_unit_match.group(2)
        
        try:
            clean_num = float(num_part)
            num_formatted = f"{clean_num:g}"
        except ValueError:
            clean_num = None
            num_formatted = num_part

        selected_unit = None
        if unit_part:
            unit_clean = unit_part.strip().lower()
            selected_unit = UNIT_MAPPINGS.get(unit_clean, unit_part.strip())
        elif fallback_unit and str(fallback_unit).strip():
            fb_clean = str(fallback_unit).strip().lower()
            selected_unit = UNIT_MAPPINGS.get(fb_clean, str(fallback_unit).strip())

        if selected_unit:
            norm_val = f"{num_formatted} {selected_unit}"
            return {
                "normalized_value": norm_val,
                "raw_value": raw_str,
                "unit": selected_unit,
                "clean_num": clean_num
            }
        else:
            return {
                "normalized_value": num_formatted,
                "raw_value": raw_str,
                "unit": None,
                "clean_num": clean_num
            }

    # Complex string or textual value
    normalized_text = re.sub(r'\s+', ' ', clean_str)
    
    for unit_raw, unit_std in UNIT_MAPPINGS.items():
        pattern = r'\b' + re.escape(unit_raw) + r'\b'
        normalized_text = re.sub(pattern, unit_std, normalized_text, flags=re.IGNORECASE)

    return {
        "normalized_value": normalized_text,
        "raw_value": raw_str,
        "unit": None,
        "clean_num": None
    }
