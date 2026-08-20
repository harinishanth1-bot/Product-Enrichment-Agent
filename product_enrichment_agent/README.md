# 🏬 Enterprise Product Data Enrichment Agent

> **Autonomous B2B/B2C Catalog Enrichment Engine Powered by Google Vertex AI Search Grounding & Pydantic v2**

---

## 📌 Quick Overview

This subfolder contains the core application code for the **Enterprise Product Data Enrichment Agent**.

- **Web Application Server**: [`app.py`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/app.py)
- **Pipeline Processing Engine**: [`run_enrichment.py`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/run_enrichment.py)
- **Core Package**: [`pd_enrichment/`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/pd_enrichment)
  - [`schemas.py`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/pd_enrichment/schemas.py): Pydantic v2 Schema & Unit Symbol Normalizer
  - [`enricher_genai.py`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/pd_enrichment/enricher_genai.py): Google Search Grounding Engine
  - [`exporter.py`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/pd_enrichment/exporter.py): Multi-Sheet Emerald Green Excel Exporter

For full documentation, architecture flowcharts, and ROI details, see the **[Master Repository README](../README.md)**.

---

## 🚀 Running Locally

```powershell
# 1. Activate Virtual Environment
.\venv\Scripts\Activate.ps1

# 2. Run Flask App
python app.py
```
Open **`http://127.0.0.1:5000/`** in your browser.
