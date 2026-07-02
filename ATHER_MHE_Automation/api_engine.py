from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
import json
import os
from datetime import datetime
from sqlmodel import Field, SQLModel, create_engine, Session

# 1. DATABASE SETUP
DATABASE_URL = os.getenv("DATABASE_URL") # Add this to Render Environment Variables
engine = create_engine(DATABASE_URL)

class DecisionLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    weights_json: str
    results_json: str

# Create tables in Postgres on startup
SQLModel.metadata.create_all(engine)

app = FastAPI(title="SPM Enterprise API", version="2.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
    weight_cost: float
    weight_tech: float
    weight_delivery: float
    weight_safety: float

@app.post("/api/v1/rank-suppliers")
def rank_suppliers(payload: SPMRequest):
    try:
        data = [s.dict() for s in payload.suppliers]
        df = pd.DataFrame(data)

        # Logic
        df['safety_penalty'] = df['has_auto_decel'].apply(lambda x: 0 if x else 50000)
        df['5_Year_TCO'] = df['base_capex'] + df['total_amc'] + df['battery_cost'] + df['safety_penalty']
        df['safety_score'] = df['has_auto_decel'].apply(lambda x: 100 if x else 0)
        
        df['final_ahp_score'] = (
            ((df['5_Year_TCO'].min() / df['5_Year_TCO']) * 100 * payload.weight_cost) +
            (df['tech_score'] * payload.weight_tech) +
            ((df['lead_time_weeks'].min() / df['lead_time_weeks']) * 100 * payload.weight_delivery) +
            (df['safety_score'] * payload.weight_safety)
        )
        
        result_data = df.sort_values(by='final_ahp_score', ascending=False).to_dict(orient='records')

        # 2. SAVE TO POSTGRES (Audit Trail)
        with Session(engine) as session:
            log = DecisionLog(
                weights_json=json.dumps(payload.dict(exclude={'suppliers'})),
                results_json=json.dumps(result_data)
            )
            session.add(log)
            session.commit()

        return {"status": "success", "data": result_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
