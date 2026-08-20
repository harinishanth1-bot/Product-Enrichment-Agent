import os
import json
from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project="analytics-online-thd", location="us-central1")

prompt = """
You are an expert product data enrichment agent with Google Search grounding capabilities.
Your task is to identify authoritative, evidence-backed values for missing product attributes with MAXIMUM COVERAGE, DYNAMIC TRUSTED SOURCE DISCOVERY, and MANDATORY STANDARDIZED UNITS.

### Product Context:
- **Product Name**: Proline® Valve Ball, 3/4", Full Port, 600 Psi Wog, 150 Psi Wsp, Brass, Lead-Free
- **Brand**: Proline / B&K ProLine
- **Size**: 3/4 inch
- **Part Number**: Proline 3/4 Full Port Ball Valve 600 WOG 150 WSP

### Target Missing Attributes to Enrich:
["Product Depth", "Product Height", "Product Width", "Product Weight", "Material"]

### SPECIFICATION TABLE SEARCH DIRECTIVE:
1. Search specifically for HD Supply, SupplyHouse, Home Depot, or Manufacturer (B&K ProLine) product detail catalog pages and specification tables for "Proline 3/4 Ball Valve 600 WOG 150 WSP Lead Free".
2. Locate the full technical specifications section / table listing physical dimensions (Depth, Height, Width, Length) and Weight.
3. Extract exact values from the spec table and standardize units (e.g. '2.5 in', '1.2 lb', 'Lead-Free Brass').

Respond strictly in JSON format:
{
  "attributes": {
    "Product Depth": {"value": "...", "unit": "...", "source": "...", "url": "...", "confidence": 90, "evidence_note": "..."},
    "Product Height": {"value": "...", "unit": "...", "source": "...", "url": "...", "confidence": 90, "evidence_note": "..."},
    "Product Width": {"value": "...", "unit": "...", "source": "...", "url": "...", "confidence": 90, "evidence_note": "..."},
    "Product Weight": {"value": "...", "unit": "...", "source": "...", "url": "...", "confidence": 90, "evidence_note": "..."},
    "Material": {"value": "...", "unit": "...", "source": "...", "url": "...", "confidence": 90, "evidence_note": "..."}
  }
}
"""

res = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=types.GenerateContentConfig(
        tools=[{"google_search": {}}],
        temperature=0.1
    )
)

print("--- GEMINI GROUNDED OUTPUT ---")
print(res.text)

if hasattr(res, 'candidates') and res.candidates:
    cand = res.candidates[0]
    if hasattr(cand, 'grounding_metadata') and cand.grounding_metadata:
        gm = cand.grounding_metadata
        print("\n--- GROUNDING SEARCH QUERIES EXECUTE BY GEMINI ---")
        if hasattr(gm, 'web_search_queries'):
            print("Search Queries:", gm.web_search_queries)
        if hasattr(gm, 'grounding_chunks'):
            print("Grounding Sources:")
            for chunk in gm.grounding_chunks:
                if hasattr(chunk, 'web'):
                    print(f"  - Title: {chunk.web.title} | URI: {chunk.web.uri}")
