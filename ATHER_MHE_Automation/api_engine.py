from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import pandas as pd
import json
import os
from datetime import datetime
from contextlib import asynccontextmanager
from sqlmodel import Field, SQLModel, create_engine, Session, select

# 1. DATABASE SETUP
class DecisionLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    weights_json: str
    results_json: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("❌ WARNING: DATABASE_URL missing!")
    else:
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        app.state.db_engine = create_engine(DATABASE_URL)
        SQLModel.metadata.create_all(app.state.db_engine)
        print("🚀 Successfully connected to Supabase and verified tables!")
    yield

app = FastAPI(title="SPM Enterprise API", version="2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 2. SECURITY LAYER
security = HTTPBearer()
API_SECRET_TOKEN = os.getenv("API_SECRET_TOKEN", "default-dev-token")

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != API_SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Access denied: Invalid authentication token.")
    return credentials.credentials

# 3. DATA MODELS
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

# 4. SECURED POST ENDPOINT (Math & Saving)
@app.post("/api/v1/rank-suppliers")
def rank_suppliers(payload: SPMRequest, token: str = Depends(verify_token)):
    try:
        data = [s.dict() for s in payload.suppliers]
        df = pd.DataFrame(data)

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

        if hasattr(app.state, "db_engine"):
            with Session(app.state.db_engine) as session:
                log = DecisionLog(
                    weights_json=json.dumps(payload.dict(exclude={'suppliers'})),
                    results_json=json.dumps(result_data)
                )
                session.add(log)
                session.commit()

        return {"status": "success", "data": result_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 5. SECURED GET ENDPOINT (Retrieving History)
@app.get("/api/v1/history")
def get_history(token: str = Depends(verify_token)):
    try:
        if hasattr(app.state, "db_engine"):
            with Session(app.state.db_engine) as session:
                # Grab the 10 most recent decisions from the database
                statement = select(DecisionLog).order_by(DecisionLog.timestamp.desc()).limit(10)
                results = session.exec(statement).all()
                return {"status": "success", "data": results}
        else:
            raise HTTPException(status_code=500, detail="Database engine not initialized")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
