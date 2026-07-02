from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd

# Initialize the Enterprise API
app = FastAPI(title="Supplier Performance Management API", version="1.0")

# Security Bypass for React Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("🟢 API Server Initializing...")

# ==========================================
# 1. DEFINE THE DATA SCHEMA (Strict Validation)
# ==========================================
class Supplier(BaseModel):
    vendor_name: str
    base_capex: float
    total_amc: float
    battery_cost: float
    lead_time_weeks: int
    tech_score: int
    has_auto_decel: bool

class SPMRequest(BaseModel):
    suppliers: List[Supplier]
    weight_cost: float = 0.40
    weight_tech: float = 0.30
    weight_delivery: float = 0.20
    weight_safety: float = 0.10

# ==========================================
# 2. THE EVALUATION ENDPOINT
# ==========================================
@app.post("/api/v1/rank-suppliers")
def rank_suppliers(payload: SPMRequest):
    try:
        # 1. Convert incoming JSON from the frontend into a Pandas DataFrame
        data = [supplier.dict() for supplier in payload.suppliers]
        df = pd.DataFrame(data)

        # 2. Calculate TCO & Safety Penalties
        df['safety_penalty'] = df['has_auto_decel'].apply(lambda x: 0 if x else 50000)
        df['5_Year_TCO'] = df['base_capex'] + df['total_amc'] + df['battery_cost'] + df['safety_penalty']
        df['safety_score'] = df['has_auto_decel'].apply(lambda x: 100 if x else 0)

        # 3. AHP Normalized Scoring
        min_tco = df['5_Year_TCO'].min()
        min_lead_time = df['lead_time_weeks'].min()

        df['norm_cost'] = (min_tco / df['5_Year_TCO']) * 100
        df['norm_delivery'] = (min_lead_time / df['lead_time_weeks']) * 100

        # Apply the weights dynamically passed from the UI
        df['final_ahp_score'] = (
            (df['norm_cost'] * payload.weight_cost) +
            (df['tech_score'] * payload.weight_tech) +
            (df['norm_delivery'] * payload.weight_delivery) +
            (df['safety_score'] * payload.weight_safety)
        )

        # 4. Sort and format the output
        df = df.sort_values(by='final_ahp_score', ascending=False)
        
        return {
            "status": "success",
            "message": "AHP Multi-Criteria Math Executed Successfully",
            "data": df[['vendor_name', 'final_ahp_score', '5_Year_TCO', 'lead_time_weeks']].to_dict(orient='records')
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
