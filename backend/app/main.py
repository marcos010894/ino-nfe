from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.database import init_db
from app.api import auth, empresas, regras_fiscais, notas

app = FastAPI(title="InnoNFe API", description="API para emissão fiscal", version="1.0.0")

# CORS Configuration
origins = [
    "http://localhost:5173",  # React app
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
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

