"""
Product Data Enrichment Pipeline Runner / CLI Orchestrator
Processes input catalog files, detects schema, performs automated parallel batched GenAI grounding, normalizes values across whole dataset, tracks granular stage & per-product/attribute timings, and exports results.
"""

import argparse
import concurrent.futures
import logging
import os
import sys
import time
import pandas as pd
from typing import Dict, Any, Optional, List

from pd_enrichment.detector import detect_columns
from pd_enrichment.normalizer import normalize_attribute_value
from pd_enrichment.enricher_genai import GroundingEnricher
from pd_enrichment.exporter import export_enrichment_results

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_enrichment")


def run_pipeline(
    input_file: str,
    output_file: str,
    evidence_json: str,
    review_csv: str,
    search_column: Optional[str] = None,
    target_attributes: Optional[List[str]] = None,
    use_genai: bool = True,
    genai_project: Optional[str] = None,
    genai_model: str = "gemini-2.5-flash",
    confidence_threshold: int = 75,
    max_search_depth: int = 3,
    max_concurrency: int = 5,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    Executes the end-to-end product data enrichment pipeline across 6 modular stages with timing metrics and dataset-wide standardization.
    """
    pipeline_t_start = time.time()
    logger.info(f"Starting product enrichment pipeline for file: {input_file} (Concurrency Cap: {max_concurrency} workers)")

    stage_timings = {}

    def notify_progress(stage_id: int, stage_name: str, message: str, pct: int, details: Optional[Dict[str, Any]] = None):
        if progress_callback:
            progress_callback({
                "stage_id": stage_id,
                "stage_name": stage_name,
                "message": message,
                "progress": pct,
                "details": details or {}
            })

    # =========================================================================
    # STAGE 1: File Ingestion & Schema Analysis
    # =========================================================================
    s1_t_start = time.time()
    notify_progress(1, "File Ingestion & Schema Analysis", "Loading catalog file and parsing column schema...", 10)
    
    if input_file.endswith(".xlsx") or input_file.endswith(".xls"):
        df = pd.read_excel(input_file)
    else:
        df = pd.read_csv(input_file)

    total_rows = len(df)
    logger.info(f"Stage 1: Loaded dataset with {total_rows} rows and {len(df.columns)} columns.")

    col_schema = detect_columns(list(df.columns), preferred_search_col=search_column)
    identity_cols = col_schema["identity_columns"]
    detected_attribute_cols = col_schema["attribute_columns"]
    primary_search_col = col_schema["primary_search_column"]

    if target_attributes and len(target_attributes) > 0:
        attribute_cols = [col for col in detected_attribute_cols if col in target_attributes]
    else:
        attribute_cols = detected_attribute_cols

    stage_timings["Stage_1_Ingestion_Sec"] = round(time.time() - s1_t_start, 3)

    notify_progress(1, "File Ingestion & Schema Analysis", f"Parsed {total_rows} rows. Found {len(identity_cols)} identity & {len(attribute_cols)} target attribute columns.", 18, {
        "total_rows": total_rows,
        "identity_cols": identity_cols,
        "attribute_cols": attribute_cols,
        "primary_search_col": primary_search_col,
        "stage_time_sec": stage_timings["Stage_1_Ingestion_Sec"]
    })

    # =========================================================================
    # STAGE 2: Target Attribute & Blank Cell Detection
    # =========================================================================
    s2_t_start = time.time()
    notify_progress(2, "Blank Cell & Target Attribute Detection", "Analyzing missing attributes across target columns...", 25)

    # Convert dataframe columns to flexible object dtype to prevent pandas int64 casting errors
    enriched_df = df.copy()
    for col in enriched_df.columns:
        enriched_df[col] = enriched_df[col].astype(object)

    # Calculate initial missing cells & catalog coverage statistics
    rows_needing_enrichment = 0
    total_missing_cells = 0
    for idx in range(total_rows):
        row = enriched_df.iloc[idx]
        missing = [col for col in attribute_cols if pd.isna(row[col]) or str(row[col]).strip() in ["", "nan", "null", "none"]]
        if missing:
            rows_needing_enrichment += 1
            total_missing_cells += len(missing)

    total_attribute_cells = total_rows * len(attribute_cols)
    initial_available_cells = max(0, total_attribute_cells - total_missing_cells)
    initial_coverage_pct = round((initial_available_cells / total_attribute_cells) * 100, 1) if total_attribute_cells > 0 else 0.0

    stage_timings["Stage_2_Blank_Detection_Sec"] = round(time.time() - s2_t_start, 3)

    notify_progress(2, "Blank Cell & Target Attribute Detection", f"Detected {total_missing_cells} missing cells across {rows_needing_enrichment} rows needing enrichment (Initial Catalog Coverage: {initial_coverage_pct}%).", 32, {
        "rows_needing_enrichment": rows_needing_enrichment,
        "total_missing_cells": total_missing_cells,
        "initial_coverage_pct": initial_coverage_pct,
        "skipped_complete_rows": total_rows - rows_needing_enrichment,
        "stage_time_sec": stage_timings["Stage_2_Blank_Detection_Sec"]
    })

    # Initialize Grounding Engine
    enricher = None
    if use_genai:
        enricher = GroundingEnricher(
            project_id=genai_project, 
            model_name=genai_model,
            max_search_depth=max_search_depth
        )
        preflight = enricher.check_preflight()
        logger.info(f"Preflight status: {preflight}")

    # Standardize ALL pre-existing non-blank values in the catalog before imputation
    s4_pre_t_start = time.time()
    for attr_col in attribute_cols:
        for idx in range(len(enriched_df)):
            val = enriched_df.at[idx, attr_col]
            if pd.notna(val) and str(val).strip() != "":
                norm = normalize_attribute_value(val)
                enriched_df.at[idx, attr_col] = norm["normalized_value"]

    # =========================================================================
    # STAGE 3: Evidence-Grounded Imputation (Parallel Execution & Timing Tracking)
    # =========================================================================
    s3_t_start = time.time()
    evidence_records = []
    filled_cells_count = 0
    flagged_cells_count = 0
    total_grounding_calls = 0

    product_timing_records = []  # List of {"sku": str, "duration_sec": float, "missing_count": int}
    attr_timing_records = {attr: [] for attr in attribute_cols}  # Map of attr -> [duration_sec]

    # Collect rows needing enrichment
    rows_to_process = []
    for idx in range(total_rows):
        row = enriched_df.iloc[idx]
        row_identity = {col: row[col] for col in identity_cols if pd.notna(row[col])}
        if primary_search_col and primary_search_col in row and pd.notna(row[primary_search_col]):
            row_identity["Primary_Identifier"] = row[primary_search_col]

        missing_attrs = [
            col for col in attribute_cols 
            if pd.isna(row[col]) or str(row[col]).strip() in ["", "nan", "null", "none"]
        ]

        if missing_attrs:
            rows_to_process.append((idx, row_identity, missing_attrs))

    total_needing_enrichment = len(rows_to_process)
    completed_count = 0
    actual_workers = min(max_concurrency, total_needing_enrichment) if total_needing_enrichment > 0 else 0

    notify_progress(3, "Evidence-Grounded Imputation", f"Automated Concurrency: Running {actual_workers} parallel workers ({total_needing_enrichment} rows needing enrichment)...", 35, {
        "active_workers": actual_workers,
        "total_rows_needing_enrichment": total_needing_enrichment,
        "max_concurrency_cap": max_concurrency
    })

    def process_row_worker(item):
        idx, row_identity, missing_attrs = item
        t_w_start = time.time()
        grounding_results = {}
        if enricher:
            grounding_results = enricher.enrich_row_attributes(row_identity, missing_attrs)
        t_w_duration = round(time.time() - t_w_start, 3)
        return idx, row_identity, missing_attrs, grounding_results, t_w_duration

    if rows_to_process and enricher:
        logger.info(f"Launching ThreadPoolExecutor with {actual_workers} workers (Auto-scaled for {total_needing_enrichment} rows)...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=actual_workers) as executor:
            future_to_row = {executor.submit(process_row_worker, item): item for item in rows_to_process}
            
            for future in concurrent.futures.as_completed(future_to_row):
                completed_count += 1
                idx, row_identity, missing_attrs, grounding_results, duration_sec = future.result()
                total_grounding_calls += 1

                sku_str = str(row_identity.get(primary_search_col, f"Row_{idx+1}"))
                prod_name_str = str(row_identity.get("Product Name", row_identity.get("title", row_identity.get("Product_Name", sku_str))))
                
                product_timing_records.append({
                    "sku": sku_str,
                    "duration_sec": duration_sec,
                    "missing_count": len(missing_attrs)
                })

                attr_share_time = round(duration_sec / max(len(missing_attrs), 1), 3)
                for attr in missing_attrs:
                    if attr in attr_timing_records:
                        attr_timing_records[attr].append(attr_share_time)

                pct = 35 + int((completed_count / total_needing_enrichment) * 45)
                notify_progress(3, "Evidence-Grounded Imputation", f"Parallel Grounding: Completed {completed_count}/{total_needing_enrichment} rows ({duration_sec}s) - SKU: {sku_str}", pct, {
                    "completed_rows": completed_count,
                    "total_rows_needing_enrichment": total_needing_enrichment,
                    "current_sku": sku_str,
                    "product_name": prod_name_str,
                    "missing_attrs": missing_attrs,
                    "active_workers": actual_workers,
                    "row_duration_sec": duration_sec
                })

                for attr in missing_attrs:
                    res = grounding_results.get(attr) or {}
                    raw_val = res.get("value")
                    unit_res = res.get("unit")
                    
                    if raw_val and str(raw_val).strip() != "" and str(raw_val).lower() not in ["null", "none"]:
                        norm = normalize_attribute_value(raw_val, fallback_unit=unit_res)
                        final_val = norm["normalized_value"]
                        unit = unit_res or norm["unit"]
                        
                        if unit and str(unit).strip() != "":
                            unit_clean = str(unit).strip()
                            if not final_val.lower().endswith(unit_clean.lower()):
                                final_val = f"{final_val} {unit_clean}"

                        enriched_df.at[idx, attr] = final_val

                        conf = int(res.get("confidence", 80)) if res.get("confidence") is not None else 80
                        flagged = conf < confidence_threshold

                        filled_cells_count += 1
                        if flagged:
                            flagged_cells_count += 1

                        evidence_records.append({
                            "Row_Index": idx + 1,
                            "SKU_ID": str(row_identity.get(primary_search_col, f"Row_{idx + 1}")),
                            "Product_Name": str(row_identity.get("Product Name", row_identity.get("title", ""))),
                            "Attribute": attr,
                            "Filled_Value": final_val,
                            "Unit": unit or "",
                            "Source": res.get("source", "Google Grounding"),
                            "Source_Type": res.get("source_type", "web"),
                            "URL": res.get("url", ""),
                            "Confidence": conf,
                            "Flagged_For_Review": flagged,
                            "Evidence_Note": res.get("evidence_note", "")
                        })

    stage_timings["Stage_3_Grounding_Imputation_Sec"] = round(time.time() - s3_t_start, 3)

    # =========================================================================
    # STAGE 4: Unit Normalization & Standardization
    # =========================================================================
    s4_t_start = time.time()
    # Final pass to ensure whole-dataset consistency
    for attr_col in attribute_cols:
        for idx in range(len(enriched_df)):
            val = enriched_df.at[idx, attr_col]
            if pd.notna(val) and str(val).strip() != "":
                norm = normalize_attribute_value(val)
                enriched_df.at[idx, attr_col] = norm["normalized_value"]

    stage_timings["Stage_4_Normalization_Sec"] = round((time.time() - s4_t_start) + (time.time() - s4_pre_t_start if 's4_pre_t_start' in locals() else 0), 3)

    notify_progress(4, "Unit Normalization & Standardization", f"Standardized physical units and values across all {len(attribute_cols)} attribute columns.", 85, {
        "stage_time_sec": stage_timings["Stage_4_Normalization_Sec"]
    })

    # =========================================================================
    # STAGE 5: Quality Audit & Confidence Validation
    # =========================================================================
    s5_t_start = time.time()
    stage_timings["Stage_5_Quality_Audit_Sec"] = round(time.time() - s5_t_start, 3)

    notify_progress(5, "Quality Audit & Confidence Validation", f"Evaluated confidence scores. {filled_cells_count - flagged_cells_count} high/med confidence, {flagged_cells_count} flagged for review (<{confidence_threshold}).", 92, {
        "stage_time_sec": stage_timings["Stage_5_Quality_Audit_Sec"]
    })

    # =========================================================================
    # STAGE 6: Export Results & Artifacts
    # =========================================================================
    s6_t_start = time.time()
    notify_progress(6, "Export & Artifact Generation", "Exporting multi-sheet enriched workbook and evidence trace...", 95)

    export_summary = export_enrichment_results(
        enriched_df=enriched_df,
        evidence_records=evidence_records,
        output_path=output_file,
        evidence_json_path=evidence_json,
        review_csv_path=review_csv,
        confidence_threshold=confidence_threshold
    )

    stage_timings["Stage_6_Export_Sec"] = round(time.time() - s6_t_start, 3)
    total_pipeline_time_sec = round(time.time() - pipeline_t_start, 3)
    stage_timings["Total_Pipeline_Duration_Sec"] = total_pipeline_time_sec

    # Compute Per-Product Timing Stats
    if product_timing_records:
        prod_durations = [r["duration_sec"] for r in product_timing_records]
        avg_prod_time = round(sum(prod_durations) / len(prod_durations), 3)
        max_prod_record = max(product_timing_records, key=lambda x: x["duration_sec"])
        min_prod_record = min(product_timing_records, key=lambda x: x["duration_sec"])
        max_prod_info = {"sku": max_prod_record["sku"], "time_sec": max_prod_record["duration_sec"]}
        min_prod_info = {"sku": min_prod_record["sku"], "time_sec": min_prod_record["duration_sec"]}
    else:
        avg_prod_time = 0.0
        max_prod_info = {"sku": "N/A", "time_sec": 0.0}
        min_prod_info = {"sku": "N/A", "time_sec": 0.0}

    # Compute Per-Attribute Timing Stats
    attr_stats_map = {}
    all_attr_durations = []
    for attr, durations in attr_timing_records.items():
        if durations:
            avg_a = round(sum(durations) / len(durations), 3)
            max_a = round(max(durations), 3)
            min_a = round(min(durations), 3)
            attr_stats_map[attr] = {"avg_sec": avg_a, "max_sec": max_a, "min_sec": min_a, "sample_count": len(durations)}
            all_attr_durations.extend([(attr, d) for d in durations])
        else:
            attr_stats_map[attr] = {"avg_sec": 0.0, "max_sec": 0.0, "min_sec": 0.0, "sample_count": 0}

    if all_attr_durations:
        avg_attr_time = round(sum(d[1] for d in all_attr_durations) / len(all_attr_durations), 3)
        max_attr_tuple = max(all_attr_durations, key=lambda x: x[1])
        min_attr_tuple = min(all_attr_durations, key=lambda x: x[1])
        max_attr_info = {"attribute": max_attr_tuple[0], "time_sec": max_attr_tuple[1]}
        min_attr_info = {"attribute": min_attr_tuple[0], "time_sec": min_attr_tuple[1]}
    else:
        avg_attr_time = 0.0
        max_attr_info = {"attribute": "N/A", "time_sec": 0.0}
        min_attr_info = {"attribute": "N/A", "time_sec": 0.0}

    timing_summary = {
        "stage_timings_sec": stage_timings,
        "total_pipeline_duration_sec": total_pipeline_time_sec,
        "per_product_stats": {
            "avg_time_per_product_sec": avg_prod_time,
            "max_time_per_product": max_prod_info,
            "min_time_per_product": min_prod_info,
            "total_products_grounded": len(product_timing_records)
        },
        "per_attribute_stats": {
            "avg_time_per_attribute_sec": avg_attr_time,
            "max_time_per_attribute": max_attr_info,
            "min_time_per_attribute": min_attr_info,
            "attribute_breakdown": attr_stats_map
        }
    }

    # Compute Catalog Coverage KPI Expansion Metrics
    final_available_cells = initial_available_cells + filled_cells_count
    final_coverage_pct = round((final_available_cells / total_attribute_cells) * 100, 1) if total_attribute_cells > 0 else 0.0
    coverage_increase_pct = round(final_coverage_pct - initial_coverage_pct, 1)

    coverage_metrics = {
        "total_attribute_cells": total_attribute_cells,
        "initial_available_cells": initial_available_cells,
        "initial_coverage_pct": initial_coverage_pct,
        "filled_cells_count": filled_cells_count,
        "final_available_cells": final_available_cells,
        "final_coverage_pct": final_coverage_pct,
        "coverage_increase_pct": coverage_increase_pct
    }

    notify_progress(6, "Export & Artifact Generation", f"Enrichment pipeline completed successfully in {total_pipeline_time_sec}s! Catalog Coverage expanded from {initial_coverage_pct}% to {final_coverage_pct}% (+{coverage_increase_pct}% gain).", 100, {
        "filled_cells": filled_cells_count,
        "flagged_cells": flagged_cells_count,
        "total_grounding_calls": total_grounding_calls,
        "coverage_metrics": coverage_metrics,
        "timing_summary": timing_summary
    })

    summary = {
        "status": "success",
        "total_rows": total_rows,
        "identity_columns": identity_cols,
        "target_attribute_columns": attribute_cols,
        "primary_search_column": primary_search_col,
        "total_grounding_api_calls": total_grounding_calls,
        "filled_cells": filled_cells_count,
        "flagged_cells": flagged_cells_count,
        "coverage_metrics": coverage_metrics,
        "timing_metrics": timing_summary,
        "output_file": output_file,
        "evidence_json": evidence_json,
        "review_csv": review_csv
    }
    
    logger.info(f"Pipeline completed: {summary}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Product Data Enrichment Agent Pipeline")
    parser.add_argument("input", help="Path to input CSV or XLSX catalog file")
    parser.add_argument("--out", required=True, help="Path for enriched output CSV or XLSX")
    parser.add_argument("--evidence", default="out/evidence.json", help="Path for evidence JSON artifact")
    parser.add_argument("--review", default="out/review.csv", help="Path for review CSV artifact")
    parser.add_argument("--search-column", help="Preferred primary search identifier column")
    parser.add_argument("--target-attributes", nargs="*", help="Optional list of specific attribute columns to enrich")
    parser.add_argument("--use-genai", action="store_true", default=True, help="Enable GenAI Google Grounding")
    parser.add_argument("--genai-project", help="GCP Project ID for Vertex AI")
    parser.add_argument("--genai-model", default="gemini-2.5-flash", help="Gemini model name")
    parser.add_argument("--confidence-threshold", type=int, default=75, help="Low confidence threshold")
    parser.add_argument("--max-search-depth", type=int, default=3, help="Max search iterations per product row")
    parser.add_argument("--max-concurrency", type=int, default=5, help="Max parallel worker threads for concurrent API hits")

    args = parser.parse_args()

    res = run_pipeline(
        input_file=args.input,
        output_file=args.out,
        evidence_json=args.evidence,
        review_csv=args.review,
        search_column=args.search_column,
        target_attributes=args.target_attributes,
        use_genai=args.use_genai,
        genai_project=args.genai_project,
        genai_model=args.genai_model,
        confidence_threshold=args.confidence_threshold,
        max_search_depth=args.max_search_depth,
        max_concurrency=args.max_concurrency
    )
    print("\n--- Enrichment Summary ---")
    for k, v in res.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
