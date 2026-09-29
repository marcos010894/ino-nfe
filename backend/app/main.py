from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.models.database import init_db
from app.api import auth, empresas, regras_fiscais, notas, integracao, admin, dashboard, contador
# Import garante que SQLModel enxergue a tabela no create_all() em fresh DB.
from app.models import envio_contador_log  # noqa: F401
from app.services.scheduler import iniciar_scheduler, parar_scheduler

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
    # Cron do envio ao contador. No-op quando ENVIO_CONTADOR_CRON_ATIVO=false
    # (dev/local por default). Ligado no VPS via env var.
    iniciar_scheduler()


@app.on_event("shutdown")
def on_shutdown():
    parar_scheduler()


@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(auth.router)
app.include_router(empresas.router)
app.include_router(regras_fiscais.router)
app.include_router(notas.router)
app.include_router(integracao.router)
app.include_router(admin.router)
app.include_router(dashboard.router)
app.include_router(contador.router)

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

    # Rotas do SPA que COLIDEM com rotas da API (ex.: `/admin/empresas`) são
    # matched pela API antes do catch-all acima. Quando o browser dá F5 nessas
    # URLs sem JWT, a API retorna 401 JSON em vez do SPA — a UI some.
    # Este middleware devolve o index.html quando: método GET + status 401/403/404
    # + Accept do request pede text/html (só browser navegando). Requests fetch
    # do axios (Accept: application/json) passam sem alteração.
    from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402

    class SpaHtmlFallbackMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            path = request.url.path
            if (
                request.method == "GET"
                and response.status_code in (401, 403, 404)
                and "text/html" in request.headers.get("accept", "")
                and not path.startswith("/assets")
                and not path.startswith("/health")
                and not path.startswith("/docs")
                and not path.startswith("/openapi")
            ):
                return FileResponse("frontend_dist/index.html")
            return response

    app.add_middleware(SpaHtmlFallbackMiddleware)
