import os
import json
from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project="analytics-online-thd", location="us-central1")

prompt = """
Find technical specification details for this product:
Product: Proline® Valve Ball, 3/4", Full Port, 600 Psi Wog, 150 Psi Wsp, Brass, Lead-Free
Target Attributes: ["Product Depth", "Product Height", "Product Width", "Product Weight"]

SEARCH DIRECTIVE:
Search specifically for the HD Supply, Home Depot, and B&K ProLine official specification tables for this 3/4" Lead Free Brass Ball Valve.
Extract Product Depth, Product Height, Product Width, and Product Weight.

Respond in JSON format with values, units, sources, and direct web URLs.
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
            print("\nGrounding Sources Returned by Google Search:")
            for chunk in gm.grounding_chunks:
                if hasattr(chunk, 'web'):
                    print(f"  - Title: {chunk.web.title} | URI: {chunk.web.uri}")
