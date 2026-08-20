"""
GenAI Grounding Enricher Module
Uses Gemini with Google Search Grounding to perform evidence-backed attribute grounding per product row.
Features a 2-Pass Targeted Grounding Loop (Pass 1 Batched -> Pass 2 Focused Multi-Hop Search for remaining nulls)
to guarantee high coverage and maximum accuracy every single time.
"""

import json
import logging
import os
import re
import time
import subprocess
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

GENAI_SDK_AVAILABLE = False
SDK_TYPE = None

try:
    from google import genai
    from google.genai import types
    GENAI_SDK_AVAILABLE = True
    SDK_TYPE = "google-genai"
except ImportError:
    try:
        import google.generativeai as genai_legacy
        GENAI_SDK_AVAILABLE = True
        SDK_TYPE = "google-generativeai"
    except ImportError:
        GENAI_SDK_AVAILABLE = False


def check_adc_token_status() -> Dict[str, Any]:
    """
    Executes a runtime check against Google Application Default Credentials (ADC) token status.
    Returns:
      {
        "adc_valid": True/False,
        "active_account": "user@domain.com",
        "active_project": "project-id",
        "error": "Error details if invalid or expired"
      }
    """
    status = {"adc_valid": False, "active_account": None, "active_project": None, "error": None}
    
    # Check active gcloud account & project
    try:
        acc_proc = subprocess.run(["gcloud.cmd", "config", "get-value", "account"], capture_output=True, text=True, timeout=8)
        if acc_proc.returncode == 0 and acc_proc.stdout.strip():
            status["active_account"] = acc_proc.stdout.strip()
    except Exception as e:
        logger.debug(f"Could not fetch gcloud account: {e}")

    try:
        proj_proc = subprocess.run(["gcloud.cmd", "config", "get-value", "project"], capture_output=True, text=True, timeout=8)
        if proj_proc.returncode == 0 and proj_proc.stdout.strip() and "unset" not in proj_proc.stdout.lower():
            status["active_project"] = proj_proc.stdout.strip()
    except Exception as e:
        logger.debug(f"Could not fetch gcloud project: {e}")

    # Check ADC token validity using print-access-token
    try:
        proc = subprocess.run(["gcloud.cmd", "auth", "application-default", "print-access-token"], capture_output=True, text=True, timeout=12)
        stdout_err = (proc.stdout or "") + " " + (proc.stderr or "")
        
        if proc.returncode == 0 and proc.stdout.strip() and not "ERROR" in proc.stdout and not "Reauthentication failed" in stdout_err:
            status["adc_valid"] = True
        else:
            if "Reauthentication failed" in stdout_err or "cannot prompt" in stdout_err or "CSRF" in stdout_err:
                status["error"] = "Google ADC OAuth Token Expired (24h limit). Re-authentication required."
            else:
                status["error"] = proc.stderr.strip() or proc.stdout.strip() or "ADC token expired or missing."
    except subprocess.TimeoutExpired:
        status["error"] = "gcloud token verification timed out. Token may be expired or requiring interactive re-auth."
    except Exception as e:
        status["error"] = f"Failed to test ADC token: {str(e)}"
        
    return status


def trigger_adc_login_terminal() -> bool:
    """
    Facilitates 1-click re-authorization by opening an interactive terminal window 
    executing 'gcloud auth application-default login --no-launch-browser'.
    """
    try:
        if os.name == "nt":
            cmd_str = 'start "Google Cloud Auth" cmd.exe /k "gcloud.cmd auth application-default login --no-launch-browser"'
            subprocess.Popen(cmd_str, shell=True)
        else:
            subprocess.Popen(["gcloud", "auth", "application-default", "login", "--no-launch-browser"])
        return True
    except Exception as e:
        logger.error(f"Failed to launch gcloud re-auth terminal: {e}")
        return False


class GroundingEnricher:
    """Grounding Engine backed by Gemini models and Google Search Grounding."""
    
    def __init__(
        self, 
        project_id: Optional[str] = None, 
        model_name: str = "gemini-2.5-flash", 
        api_key: Optional[str] = None,
        max_search_depth: int = 3
    ):
        if not project_id:
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT_ID")
            if not project_id:
                try:
                    p_proc = subprocess.run(["gcloud.cmd", "config", "get-value", "project"], capture_output=True, text=True, timeout=5)
                    if p_proc.returncode == 0 and p_proc.stdout.strip() and "unset" not in p_proc.stdout.lower():
                        project_id = p_proc.stdout.strip()
                except Exception:
                    pass

        self.project_id = project_id
        self.model_name = model_name or "gemini-2.5-flash"
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self.max_search_depth = max(1, min(max_search_depth, 10))  # Depth range 1 to 10
        self.client = None
        self.legacy_model = None
        self.init_error = None
        
        self._initialize_client()

    def _initialize_client(self):
        """Initializes the appropriate Google GenAI client based on available credentials."""
        if not GENAI_SDK_AVAILABLE:
            self.init_error = "GenAI SDK packages not installed."
            return

        if SDK_TYPE == "google-genai":
            if self.project_id:
                try:
                    self.client = genai.Client(vertexai=True, project=self.project_id, location="us-central1")
                    logger.info(f"Initialized Vertex AI genai.Client (Project: {self.project_id}, Model: {self.model_name})")
                    return
                except Exception as e:
                    logger.warning(f"Vertex AI client init failed: {e}")
                    self.init_error = str(e)

            if self.api_key:
                try:
                    self.client = genai.Client(api_key=self.api_key)
                    logger.info(f"Initialized Gemini API Key genai.Client (Model: {self.model_name})")
                    return
                except Exception as e:
                    logger.warning(f"API key client init failed: {e}")
                    self.init_error = str(e)

            try:
                self.client = genai.Client()
                logger.info(f"Initialized default genai.Client (Model: {self.model_name})")
            except Exception as e:
                logger.warning(f"Default genai.Client init failed: {e}")
                self.init_error = str(e)

        elif SDK_TYPE == "google-generativeai":
            try:
                if self.api_key:
                    genai_legacy.configure(api_key=self.api_key)
                self.legacy_model = genai_legacy.GenerativeModel(self.model_name)
                logger.info(f"Initialized google-generativeai model ({self.model_name})")
            except Exception as e:
                logger.error(f"Failed to initialize google-generativeai model: {e}")
                self.init_error = str(e)

    def check_preflight(self) -> Dict[str, Any]:
        """Preflight system check for GenAI client & ADC availability."""
        adc_status = check_adc_token_status()
        active_proj = self.project_id or adc_status.get("active_project")
        
        status = {
            "genai_sdk_installed": GENAI_SDK_AVAILABLE,
            "sdk_type": SDK_TYPE,
            "client_initialized": self.client is not None or self.legacy_model is not None,
            "project_id": active_proj,
            "model_name": self.model_name,
            "adc_valid": adc_status["adc_valid"],
            "active_account": adc_status["active_account"],
            "active_project": active_proj,
            "errors": []
        }
        
        if not GENAI_SDK_AVAILABLE:
            status["errors"].append("GenAI SDK not installed. Please install 'google-genai' or 'google-generativeai'.")
            
        if not adc_status["adc_valid"] and not self.api_key:
            status["errors"].append(f"ADC Token Issue: {adc_status['error'] or 'Token expired or unauthenticated.'}")

        if not status["client_initialized"]:
            err_msg = self.init_error or "GenAI Client failed to initialize. Set GOOGLE_CLOUD_PROJECT or GEMINI_API_KEY."
            status["errors"].append(err_msg)
            
        return status

    def enrich_row_attributes(
        self, 
        row_identity: Dict[str, Any], 
        missing_attributes: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Executes a 2-Pass Grounding Engine for Maximum Coverage Every Time:
          - Pass 1: Primary Batched Grounding Request across priority sources.
          - Pass 2 (Targeted Fallback): If any attributes remain null/missing after Pass 1,
            constructs a hyper-focused Pass 2 search query specifically targeting remaining nulls.
        """
        if not missing_attributes:
            return {}

        if not self.client and not self.legacy_model:
            logger.warning("GenAI client not initialized. Returning empty grounding defaults.")
            return {attr: self._empty_attribute_response() for attr in missing_attributes}

        # --- PASS 1: Primary Batched Search Grounding ---
        prompt_p1 = self._build_batched_prompt(row_identity, missing_attributes, pass_num=1)
        pass1_results = self._execute_grounded_with_retry(prompt_p1, missing_attributes)

        # Identify remaining null/unfilled attributes after Pass 1
        still_missing = [
            attr for attr in missing_attributes
            if not pass1_results.get(attr) or not pass1_results[attr].get("value")
        ]

        # If all attributes grounded in Pass 1, return immediately
        if not still_missing:
            return pass1_results

        # --- PASS 2: Targeted Multi-Hop Search Grounding for Remaining Nulls ---
        logger.info(f"Row {row_identity.get('Primary_Identifier')}: Running Pass 2 Targeted Search for remaining nulls: {still_missing}")
        prompt_p2 = self._build_batched_prompt(row_identity, still_missing, pass_num=2)
        pass2_results = self._execute_grounded_with_retry(prompt_p2, still_missing)

        # Merge Pass 2 grounded values into Pass 1 results
        final_results = dict(pass1_results)
        for attr in still_missing:
            p2_item = pass2_results.get(attr)
            if p2_item and p2_item.get("value"):
                final_results[attr] = p2_item

        return final_results

    def _execute_grounded_with_retry(self, prompt: str, target_attributes: List[str]) -> Dict[str, Dict[str, Any]]:
        """Executes grounded generation with exponential backoff for rate limits."""
        max_retries = 3
        retry_delay = 2.0

        for attempt in range(max_retries):
            try:
                raw_response_text = self._execute_grounded_generation(prompt)
                parsed_data = self._parse_and_repair_json(raw_response_text, target_attributes)
                return parsed_data
            except Exception as e:
                err_str = str(e).lower()
                if ("429" in err_str or "quota" in err_str or "resource_exhausted" in err_str) and attempt < max_retries - 1:
                    logger.warning(f"Quota retry in {retry_delay}s (Attempt {attempt+1}/{max_retries})...")
                    time.sleep(retry_delay)
                    retry_delay *= 2.0
                else:
                    logger.error(f"Grounding generation failed: {e}")
                    return {attr: self._empty_attribute_response() for attr in target_attributes}

        return {attr: self._empty_attribute_response() for attr in target_attributes}

    def _build_batched_prompt(self, row_identity: Dict[str, Any], missing_attributes: List[str], pass_num: int = 1) -> str:
        ident_str = "\n".join([f"- **{k}**: {v}" for k, v in row_identity.items() if v and str(v).strip() != ""])
        missing_str = ", ".join([f'"{attr}"' for attr in missing_attributes])
        depth = getattr(self, "max_search_depth", 3)
        
        full_name_val = str(row_identity.get("Product Name") or row_identity.get("Product_Name") or (list(row_identity.values())[0] if row_identity else "")).strip()

        pass_instruction = ""
        if pass_num == 2:
            pass_instruction = f"""
### PASS 2 TARGETED HIGH-COVERAGE EXTRACTION INSTRUCTION:
Pass 1 search did not find values for: [{missing_str}].
You MUST execute focused search queries specifically searching for these exact missing attributes:
1. Search specifically for: "{full_name_val} Assembled Dimensions {missing_attributes[0]} spec table"
2. Search specifically for: "{full_name_val} technical specifications datasheet PDF {missing_str}"
3. Thoroughly inspect HTML specification tables, accordions, product feature lists, and technical descriptions on major distributor portals and manufacturer websites.
"""

        prompt = f"""
You are an expert product data enrichment agent with Google Search grounding capabilities.
Your task is to identify authoritative, evidence-backed values for missing product attributes with MAXIMUM COVERAGE, DYNAMIC PRIORITY SOURCE RANKING, and MANDATORY STANDARDIZED UNITS.

### Product Context:
{ident_str}

### Target Missing Attributes to Enrich:
[{missing_str}]
{pass_instruction}

### DYNAMIC PRIORITY SOURCE RANKING HIERARCHY:
Rank and prioritize Google Search Grounding sources strictly in this category hierarchy:
1. **Priority 1 (Highest Authority)**: Official OEM / Manufacturer Websites & Official PDF Technical Spec Sheets matching the product's brand.
2. **Priority 2 (Big Trusted Retailers & Distributors)**: Major Category Distributors & B2B Retail Catalog Sites matching the product category.
3. **Priority 3**: Other Category-Specific Authorized Distributors & Retailers.
4. **Priority 4 (REJECT / DO NOT USE)**: Unverified personal blogs, social media posts, Q&A forums, and unvetted third-party marketplace listings.

### DYNAMIC FULL-STRING SEARCH & MULTI-SECTION TECHNICAL EXTRACTION DIRECTIVE:
1. Full-String Base Product Query:
   - ALWAYS use the full text string from the product name column: "{full_name_val}" as the core product search identifier. Do NOT shorten or cut the product string.

2. Fully Dynamic Attribute Search Strategy:
   - Formulate live search queries dynamically combining the full product string with the exact target missing attributes required for this row: [{missing_str}].
   - Dynamically execute search queries tailored to the target attributes:
     * Primary Search Query: "{full_name_val} {missing_str}"
     * Specifications Query: "{full_name_val} Product Specifications Product Features {missing_str}"
     * Technical/PDF Query: "{full_name_val} Assembled Dimensions Technical Details spec sheet PDF {missing_str}"

3. Dynamic Page Section & Feature List Extraction:
   - Dynamically search for every missing attribute in [{missing_str}] across ALL web page layouts and dynamic section headers:
     * **Product Specifications Tables** (e.g., "Specifications", "Technical Specs", "Item Details", "Product Overview")
     * **Assembled Dimensions Sections** (e.g., "Assembled Dimensions", "Measurements", "Dimensions & Weights")
     * **Product Features & Highlight Bullet Lists** (e.g., "Key Features", "Highlights", "Product Characteristics")
     * **Technical Descriptions & Overview Paragraphs** (e.g., "Description", "Specifications Summary", "Features")
     * **Downloadable Technical Manuals & PDF Spec Sheets**

4. Dynamic Synonym & Variant Matching:
   - Dynamically match and resolve every requested attribute in [{missing_str}] regardless of varying label terminology, header names, or unit formats used across different supplier or retailer portals.

### ITERATIVE MULTI-SOURCE SEARCH STRATEGY (Search Depth: Up to {depth} Iterations):
- Perform up to {depth} search iterations per row, moving systematically through the source priority hierarchy (Manufacturer -> Big Trusted Retailers -> Other Retailers) until all missing attributes are confirmed or {depth} search iterations are completed.
- STOP CONDITION: Perform AT MOST {depth} search iterations per row. Do NOT invent or guess values.

### EVIDENCE TRACKING & CONFIDENCE EVALUATION:
For each enriched missing attribute, report:
- `source`: Specific name/domain of the authoritative source used (dynamically discovered, e.g. "Manufacturer Official Site", "Big Trusted Retailer").
- `source_type`: Category of source ("manufacturer" | "authorized_distributor" | "retailer" | "marketplace").
- `url`: Direct web URL where the specification table entry was confirmed.
- `confidence`: Integer confidence score (0 to 100) based on source hierarchy:
    * 90–100: Official Manufacturer / OEM Datasheet or Big Trusted Retailer Specification Table.
    * 80–89: Category-Specific Authorized Distributor Technical Specification Table.
    * 70–79: General Retailer Listing.
    * < 70: Secondary Marketplace or Unverified Source.
- `evidence_note`: Exact textual quote or specification table entry from the web page confirming the value.

### MANDATORY UNIT STANDARDIZATION REQUIREMENT:
- For dimensional metrics (Depth, Height, Width, Length, Size, Diameter, Thickness), weight/load metrics (Weight, Capacity), electrical metrics (Voltage, Wattage, Amperage), temperature metrics (Operating Temp), pressure metrics (PSI, Bar):
  --> ALWAYS include the explicit physical unit in the 'value' field (e.g., '2.64 in', '1.56 in', '0.61 lb', '120 W', '70 °F').
  --> Fill the 'unit' field with the standardized unit symbol ('in', 'ft', 'lb', 'kg', 'oz', 'V', 'W', 'A', 'Hz', '°F', '°C').
  --> NEVER output plain unitless numerals like '2.64' or '0.61' for physical/dimensional/electrical metrics. Combine the number and unit in 'value' (e.g. '2.64 in').

### Output Requirement:
Respond strictly with a valid JSON object mapping each missing attribute name to its extracted details.
Do not include any introductory text or markdown commentary outside the JSON block.

JSON Schema format required:
{{
  "attributes": {{
    "<Attribute_Name>": {{
      "value": "explicit string with unit if applicable (e.g. '2.64 in', '0.61 lb', 'Lead-Free Brass') or null if not found",
      "unit": "explicit unit string like 'in', 'lb', 'V', 'W', '°F' or null",
      "source": "Name/domain of top authoritative source",
      "source_type": "manufacturer | authorized_distributor | retailer | marketplace",
      "url": "direct URL where specification table was confirmed or null",
      "confidence": integer_score_0_to_100,
      "evidence_note": "Exact specification table entry or quote from source page"
    }}
  }}
}}
"""
        return prompt

    def _execute_grounded_generation(self, prompt: str) -> str:
        """Executes Gemini generation with Google Search Grounding tool enabled."""
        if SDK_TYPE == "google-genai" and self.client:
            config = types.GenerateContentConfig(
                tools=[{"google_search": {}}],
                temperature=0.1
            )
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            return response.text

        elif SDK_TYPE == "google-generativeai" and self.legacy_model:
            response = self.legacy_model.generate_content(
                prompt,
                generation_config={"temperature": 0.1}
            )
            return response.text

        raise RuntimeError("No active GenAI client available.")

    def _parse_and_repair_json(
        self, 
        response_text: str, 
        missing_attributes: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Parses response JSON and applies model-assisted repair if malformed."""
        if not response_text:
            return {attr: self._empty_attribute_response() for attr in missing_attributes}

        clean_text = response_text.strip()
        if "```" in clean_text:
            clean_text = re.sub(r'^```(?:json)?\s*', '', clean_text, flags=re.MULTILINE)
            clean_text = re.sub(r'```\s*$', '', clean_text, flags=re.MULTILINE).strip()

        try:
            data = json.loads(clean_text)
            attr_dict = data.get("attributes", data)
            return self._format_attribute_dictionary(attr_dict, missing_attributes)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON decode failed ({e}). Attempting JSON repair fallback...")
            repaired_text = self._repair_json_with_model(clean_text)
            try:
                data = json.loads(repaired_text)
                attr_dict = data.get("attributes", data)
                return self._format_attribute_dictionary(attr_dict, missing_attributes)
            except Exception as rep_e:
                logger.error(f"JSON repair failed: {rep_e}")
                return {attr: self._empty_attribute_response() for attr in missing_attributes}

    def _repair_json_with_model(self, malformed_json: str) -> str:
        repair_prompt = f"""
Fix the syntax errors in the following text to make it valid JSON. 
Output ONLY the raw valid JSON string and nothing else.

Text to fix:
{malformed_json}
"""
        try:
            if SDK_TYPE == "google-genai" and self.client:
                res = self.client.models.generate_content(
                    model=self.model_name,
                    contents=repair_prompt,
                    config=types.GenerateContentConfig(temperature=0.0)
                )
                text = res.text.strip()
                if "```" in text:
                    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
                    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE).strip()
                return text
        except Exception as e:
            logger.error(f"Model repair attempt error: {e}")
            
        return malformed_json

    def _format_attribute_dictionary(self, raw_dict: dict, missing_attributes: List[str]) -> Dict[str, Dict[str, Any]]:
        from pd_enrichment.schemas import EnrichedAttributeItem
        result = {}
        for attr in missing_attributes:
            item = raw_dict.get(attr) or raw_dict.get(attr.lower()) or {}
            
            # Apply Pydantic v2 validation & unit standardization
            try:
                conf_val = item.get("confidence")
                try:
                    conf_int = int(conf_val) if conf_val is not None else 80
                    conf_int = max(0, min(conf_int, 100))
                except Exception:
                    conf_int = 80

                pyd_item = EnrichedAttributeItem(
                    value=item.get("value"),
                    unit=item.get("unit"),
                    source=str(item.get("source") or "Google Grounding"),
                    source_type=str(item.get("source_type") or "web"),
                    url=item.get("url"),
                    confidence=conf_int,
                    evidence_note=str(item.get("evidence_note") or "")
                )
                result[attr] = pyd_item.model_dump()
            except Exception as ve:
                logger.warning(f"Pydantic validation fallback for '{attr}': {ve}")
                val = item.get("value")
                if val is not None and str(val).strip().lower() in ["null", "none", "n/a", ""]:
                    val = None
                result[attr] = {
                    "value": str(val).strip() if val is not None else None,
                    "unit": item.get("unit"),
                    "source": item.get("source", "Google Grounding"),
                    "source_type": item.get("source_type", "web"),
                    "url": item.get("url"),
                    "confidence": 80,
                    "evidence_note": item.get("evidence_note", "")
                }
        return result

    def _empty_attribute_response(self) -> Dict[str, Any]:
        from pd_enrichment.schemas import EnrichedAttributeItem
        return EnrichedAttributeItem(
            value=None,
            unit=None,
            source=None,
            source_type=None,
            url=None,
            confidence=0,
            evidence_note="No groundable evidence found."
        ).model_dump()

