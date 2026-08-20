import os
import pandas as pd

base_dir = os.path.dirname(os.path.abspath(__file__))
csv_path = os.path.join(base_dir, "sample_catalog.csv")
xlsx_path = os.path.join(base_dir, "sample_catalog.xlsx")

df = pd.read_csv(csv_path)
df.to_excel(xlsx_path, index=False)
print("Created sample_catalog.xlsx successfully")
