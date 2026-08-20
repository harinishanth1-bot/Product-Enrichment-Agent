# 🔬 Enterprise Product Data Enrichment Agent (Application Subfolder)

> **End-to-End Data Science Solution for Automated B2B/B2C Catalog Intelligence using Vertex AI Search Grounding, Deterministic Pydantic v2 Schema Enforcement, and Adaptive Null-Recovery**

---

## 📌 Subfolder Overview

This directory contains the core application modules and web service for the **Product Data Enrichment Agent**:

- **Flask Web Server & Async Task Queue**: [`app.py`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/app.py)
- **Pipeline Orchestrator**: [`run_enrichment.py`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/run_enrichment.py)
- **Data Science & Validation Core**: [`pd_enrichment/`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/pd_enrichment)
  - [`schemas.py`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/pd_enrichment/schemas.py): Pydantic v2 In-Memory Schema & Unit Standardizer
  - [`enricher_genai.py`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/pd_enrichment/enricher_genai.py): Google Search Grounding Engine
  - [`exporter.py`](file:///C:/Users/hravic02/.gemini/antigravity/scratch/product_enrichment_repo/product_enrichment_agent/pd_enrichment/exporter.py): Multi-Sheet Emerald Green Excel Exporter

For complete business context, data science problem formulation, architecture flowcharts, and ROI metrics, please refer to the **[Master Repository README](../README.md)**.

---

## 🚀 Quickstart

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run Flask Application
python app.py
```
Open **`http://127.0.0.1:5000/`** in your browser.
