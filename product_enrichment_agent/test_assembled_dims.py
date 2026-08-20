import os
import json
from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project="analytics-online-thd", location="us-central1")

prompt = """
Product: Proline® Valve Ball, 3/4", Full Port, 600 Psi Wog, 150 Psi Wsp, Brass, Lead-Free
Target Missing Attributes to Enrich: ["Product Height", "Product Width", "Product Weight"]

SPECIFICATION TABLE DIRECTIVE:
Search specifically for HD Supply "Assembled Dimensions" specification table for this Proline 3/4" Ball Valve.
Look for "Product Height", "Product Width", "Product Weight" under Assembled Dimensions on HD Supply.

Respond strictly in JSON format:
{
  "attributes": {
    "Product Height": {"value": "...", "unit": "in", "source": "HD Supply", "confidence": 95},
    "Product Width": {"value": "...", "unit": "in", "source": "HD Supply", "confidence": 95},
    "Product Weight": {"value": "...", "unit": "lb", "source": "HD Supply", "confidence": 95}
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

print("--- GEMINI GROUNDED ASSEMBLED DIMENSIONS OUTPUT ---")
print(res.text)
