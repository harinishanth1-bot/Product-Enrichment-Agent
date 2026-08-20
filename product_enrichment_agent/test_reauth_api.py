"""
Test ADC preflight and reauth helper
"""

from pd_enrichment.enricher_genai import check_adc_token_status, GroundingEnricher

def test_adc_check():
    status = check_adc_token_status()
    print("ADC Status Check:", status)
    
    enricher = GroundingEnricher()
    preflight = enricher.check_preflight()
    print("Preflight Status:", preflight)

if __name__ == "__main__":
    test_adc_check()
