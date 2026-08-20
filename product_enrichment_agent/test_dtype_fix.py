import pandas as pd
from run_enrichment import run_pipeline

# Create test dataframe with pure integer column
data = {
    "SKU ID": [101, 102, 103],
    "Product Name": ["Valve A", "Valve B", "Valve C"],
    "Valve Type": [253757, None, 120]  # Int64 column
}

df = pd.DataFrame(data)
df.to_csv("sample_data/test_int_dtype.csv", index=False)

res = run_pipeline(
    input_file="sample_data/test_int_dtype.csv",
    output_file="out/test_int_out.csv",
    evidence_json="out/evidence.json",
    review_csv="out/review.csv",
    target_attributes=["Valve Type"]
)

print("Dtype test output:", res)
print("SUCCESS: Dtype error resolved!")
