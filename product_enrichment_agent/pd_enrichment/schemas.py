"""
Pydantic v2 Centralized Data Schemas, Normalization & Validation Module
Provides schema definitions, unit standardization, and confidence score validation for GenAI attribute grounding.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator


UNIT_SYNONYM_MAP = {
    # Dimensions & Length
    'inches': 'in', 'inch': 'in', 'in.': 'in', 'in': 'in',
    'feet': 'ft', 'foot': 'ft', 'ft.': 'ft', 'ft': 'ft',
    'millimeters': 'mm', 'millimeter': 'mm', 'mm.': 'mm', 'mm': 'mm',
    'centimeters': 'cm', 'centimeter': 'cm', 'cm.': 'cm', 'cm': 'cm',
    'meters': 'm', 'meter': 'm', 'm.': 'm', 'm': 'm',
    
    # Weight & Mass
    'pounds': 'lb', 'pound': 'lb', 'lbs': 'lb', 'lb.': 'lb', 'lb': 'lb',
    'kilograms': 'kg', 'kilogram': 'kg', 'kgs': 'kg', 'kg.': 'kg', 'kg': 'kg',
    'ounces': 'oz', 'ounce': 'oz', 'oz.': 'oz', 'oz': 'oz',
    
    # Electrical & Power
    'volts': 'V', 'volt': 'V', 'v': 'V',
    'watts': 'W', 'watt': 'W', 'w': 'W',
    'amperes': 'A', 'amps': 'A', 'amp': 'A', 'a': 'A',
    'hertz': 'Hz', 'hz': 'Hz',
    
    # Temperature & Pressure
    'fahrenheit': '°F', 'deg f': '°F', 'f': '°F', '°f': '°F',
    'celsius': '°C', 'deg c': '°C', 'c': '°C', '°c': '°C',
    'psi': 'PSI', 'wog': 'WOG', 'bar': 'Bar'
}


class EnrichedAttributeItem(BaseModel):
    """Schema model for an enriched product attribute with integrated validation and unit normalization."""
    value: Optional[str] = Field(default=None, description="Enriched value with explicit unit e.g. '2.64 in'")
    numeric_value: Optional[float] = Field(default=None, description="Numeric float component if applicable")
    unit: Optional[str] = Field(default=None, description="Standardized physical unit symbol e.g. 'in', 'lb'")
    source: Optional[str] = Field(default="Google Grounding", description="Name/domain of authoritative source")
    source_type: Optional[str] = Field(default="web", description="manufacturer | authorized_distributor | retailer | marketplace")
    url: Optional[str] = Field(default=None, description="Direct URL evidence link")
    confidence: int = Field(default=80, ge=0, le=100, description="Integer confidence score between 0 and 100")
    evidence_note: str = Field(default="", description="Exact textual quote or specification table snippet")

    @field_validator('unit', mode='before')
    @classmethod
    def standardize_unit_symbol(cls, v: Optional[str]) -> Optional[str]:
        """Automatically normalizes unit variations to standardized symbols ('inches' -> 'in')."""
        if v is None:
            return None
        clean_v = str(v).strip().lower()
        if not clean_v or clean_v in ["null", "none", "n/a"]:
            return None
        return UNIT_SYNONYM_MAP.get(clean_v, clean_v.upper())

    @field_validator('value', mode='before')
    @classmethod
    def clean_null_values(cls, v: Any) -> Optional[str]:
        """Cleans empty string representations into True None."""
        if v is None:
            return None
        s = str(v).strip()
        if s.lower() in ["null", "none", "n/a", "unknown", ""]:
            return None
        return s


class CatalogRowEnrichmentResult(BaseModel):
    """Schema model wrapping all missing attribute outputs for a catalog product row."""
    attributes: Dict[str, EnrichedAttributeItem] = Field(default_factory=dict)
