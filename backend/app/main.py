from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.database import init_db
from app.api import auth, empresas, regras_fiscais, notas, integracao

app = FastAPI(title="InnoNFe API", description="API para emissão fiscal", version="1.0.0")

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(auth.router)
app.include_router(empresas.router)
app.include_router(regras_fiscais.router)
app.include_router(notas.router)
app.include_router(integracao.router)

# Servir o frontend (React dist)
import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

if os.path.exists("frontend_dist"):
    app.mount("/assets", StaticFiles(directory="frontend_dist/assets"), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        path = os.path.join("frontend_dist", full_path)
        if os.path.isfile(path):
            return FileResponse(path)
        return FileResponse("frontend_dist/index.html")
