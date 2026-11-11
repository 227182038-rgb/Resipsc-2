from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import os

app = FastAPI(
    title="Resipsc V3 Inference Service",
    description="Decoupled inference microservice for residual PSC detection",
    version="3.0.0-alpha"
)

class InferenceRequest(BaseModel):
    batch_id: str
    file_path: str
    config_override: dict = {}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "resipsc-inference"}

@app.post("/predict")
async def predict(request: InferenceRequest, background_tasks: BackgroundTasks):
    if not os.path.exists(request.file_path):
        raise HTTPException(status_code=404, detail="Input file not found")
    
    # In Cycle 1, this will trigger the worker queue (Celery/Redis)
    return {
        "status": "accepted",
        "batch_id": request.batch_id,
        "message": "Inference job submitted to worker queue"
    }
