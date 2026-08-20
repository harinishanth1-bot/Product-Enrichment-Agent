from pd_enrichment.enricher_genai import GroundingEnricher, check_adc_token_status

adc = check_adc_token_status()
print("ADC Status:", adc)

# Test initializing with sample project or default vertex client
enricher = GroundingEnricher(project_id="home-depot-test-project")
preflight = enricher.check_preflight()
print("Preflight Status:", preflight)
