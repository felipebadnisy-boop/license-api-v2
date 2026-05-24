from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime, timedelta
import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Any
from pydantic import BaseModel, Field
import os
import re
import jwt
import logging
import sqlite3
import hashlib
import json

# =========================================================
# CONFIGURACOES
# =========================================================

SECRET_KEY = os.environ.get('JWT_SECRET_KEY', 'minha-chave-secreta-mude-em-producao-123456')
JWT_EXPIRATION = 86400  # 24 horas
JWT_ALGORITHM = "HS256"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =========================================================
# MODELOS PYDANTIC
# =========================================================

class ActivateRequest(BaseModel):
    key: str
    hwid: str

class VerifyRequest(BaseModel):
    key: str
    hwid: str

class HeartbeatRequest(BaseModel):
    key: str
    hwid: str

class AdminLoginRequest(BaseModel):
    username: str
    password: str

class CreateProductRequest(BaseModel):
    nome: str
    descricao: Optional[str] = ""

class CreateLicenseRequest(BaseModel):
    produto_slug: str
    plano: str

class RevokeLicenseRequest(BaseModel):
    key: str
    motivo: Optional[str] = "Revogada por admin"

class APIResponse(BaseModel):
    status: bool
    mensagem: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    dados: Optional[Any] = None

# =========================================================
# FUNCOES AUXILIARES
# =========================================================

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, password_hash: str) -> bool:
    return hash_password(password) == password_hash

def gerar_chave_formatada():
    partes = []
    for _ in range(4):
        parte = str(uuid.uuid4())[:4].upper()
        partes.append(parte)
    return f"{partes[0]}-{partes[1]}-{partes[2]}-{partes[3]}"

def gerar_slug(nome):
    slug = nome.lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    slug = slug.strip('-')
    return slug

# =========================================================
# BANCO DE DADOS SQLITE
# =========================================================

DB_PATH = 'licenses.db'

def init_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            descricao TEXT,
            criado_em TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS licencas (
            id TEXT PRIMARY KEY,
            key TEXT UNIQUE NOT NULL,
            produto_slug TEXT NOT NULL,
            plano TEXT NOT NULL,
            status TEXT NOT NULL,
            hwid TEXT,
            ativada_em TEXT,
            data_expiracao TEXT,
            criada_em TEXT NOT NULL,
            criada_por TEXT,
            ultima_verificacao TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessoes_ativas (
            id TEXT PRIMARY KEY,
            licenca_id TEXT NOT NULL,
            hwid TEXT NOT NULL,
            key TEXT NOT NULL,
            iniciada_em TEXT NOT NULL,
            ultimo_heartbeat TEXT NOT NULL,
            heartbeats INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id TEXT PRIMARY KEY,
            acao TEXT NOT NULL,
            entidade_id TEXT,
            detalhes TEXT,
            ip TEXT,
            timestamp TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            ultimo_login TEXT
        )
    ''')
    
    conn.commit()
    
    cursor.execute("SELECT * FROM admin_users WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO admin_users (id, username, password_hash, criado_em) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), 'admin', hash_password('36791788'), datetime.now().isoformat())
        )
        conn.commit()
    
    conn.close()
    logger.info("Banco de dados inicializado")

def get_db():
    return sqlite3.connect(DB_PATH)

init_database()

# =========================================================
# RATE LIMIT
# =========================================================

rate_limit_store = {}

def rate_limit_check(ip: str, limit: int = 100, window: int = 60) -> bool:
    now = datetime.now().timestamp()
    key = f"rate_limit:{ip}"
    
    if key not in rate_limit_store:
        rate_limit_store[key] = []
    
    rate_limit_store[key] = [ts for ts in rate_limit_store[key] if now - ts < window]
    
    if len(rate_limit_store[key]) >= limit:
        return False
    
    rate_limit_store[key].append(now)
    return True

# =========================================================
# SECURITY
# =========================================================

security = HTTPBearer()

async def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        if payload.get('role') != 'admin':
            raise HTTPException(status_code=403, detail="Acesso nao autorizado.")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalido.")

def registrar_log(acao: str, entidade_id: str, detalhes: str, ip: str = "unknown"):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (id, acao, entidade_id, detalhes, ip, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), acao, entidade_id, detalhes, ip, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    logger.info(f"LOG: {acao} - {detalhes}")

def verificar_expiracao_licenca(licenca: dict):
    if licenca["plano"] == "lifetime":
        return False
    if not licenca["data_expiracao"]:
        return False
    data_expiracao = datetime.fromisoformat(licenca["data_expiracao"])
    if datetime.now() > data_expiracao:
        if licenca["status"] == "active":
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE licencas SET status = 'expired' WHERE id = ?", (licenca["id"],))
            conn.commit()
            conn.close()
            registrar_log("license_expired", licenca["id"], f"Licenca {licenca['key']} expirou")
        return True
    return False

async def limpar_sessoes_inativas():
    limite = (datetime.now() - timedelta(minutes=5)).isoformat()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessoes_ativas WHERE ultimo_heartbeat < ?", (limite,))
    conn.commit()
    conn.close()

# =========================================================
# SCHEDULER DE LIMPEZA
# =========================================================

async def scheduler_limpeza_sessoes():
    backoff = 1
    max_backoff = 60
    
    while True:
        conn = None
        try:
            await asyncio.sleep(60)
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            timeout_online = 90
            limite_online = (datetime.now() - timedelta(seconds=timeout_online)).isoformat()
            cursor.execute("DELETE FROM sessoes_ativas WHERE ultimo_heartbeat < ?", (limite_online,))
            removidas = cursor.rowcount
            conn.commit()
            if removidas > 0:
                logger.info(f"Limpeza de sessões: {removidas} sessões removidas")
            backoff = 1
        except Exception as e:
            logger.error(f"Erro na limpeza de sessões: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        finally:
            if conn:
                conn.close()

# =========================================================
# FASTAPI APP
# =========================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando License Server...")
    asyncio.create_task(scheduler_limpeza_sessoes())
    logger.info("Scheduler de limpeza iniciado")
    yield
    logger.info("License Server desligado")

app = FastAPI(
    title="License Server API",
    description="API de gerenciamento de licencas",
    version="4.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PLANOS = {
    "trial_2min": {"nome": "Teste Rapido", "duracao_minutos": 2, "tipo": "trial"},
    "trial_3h": {"nome": "Teste Gratis", "duracao_minutos": 180, "tipo": "trial"},
    "1day": {"nome": "1 Dia", "duracao_minutos": 1440, "tipo": "pago"},
    "30days": {"nome": "30 Dias", "duracao_minutos": 43200, "tipo": "pago"},
    "365days": {"nome": "1 Ano", "duracao_minutos": 525600, "tipo": "pago"},
    "lifetime": {"nome": "Licenca Vitalicia", "duracao_minutos": None, "tipo": "lifetime"}
}

async def rate_limit_middleware(request: Request):
    ip = request.client.host
    if not rate_limit_check(ip, limit=100, window=60):
        raise HTTPException(status_code=429, detail="Rate limit excedido")
    return True

# =========================================================
# ROTAS PUBLICAS
# =========================================================

@app.get("/", response_model=APIResponse)
async def home(request: Request, _: bool = Depends(rate_limit_middleware)):
    return APIResponse(status=True, mensagem="License Server API Online")

@app.post("/activate", response_model=APIResponse)
async def activate(request: Request, req: ActivateRequest, _: bool = Depends(rate_limit_middleware)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM licencas WHERE key = ?", (req.key,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        registrar_log("activation_failed", "unknown", f"Chave invalida: {req.key}", request.client.host)
        raise HTTPException(status_code=404, detail="Chave invalida.")
    
    licenca = {
        "id": result[0], "key": result[1], "plano": result[3],
        "status": result[4], "hwid": result[5], "data_expiracao": result[7]
    }
    
    if licenca["status"] == "revoked":
        conn.close()
        raise HTTPException(status_code=403, detail="Licenca revogada.")
    
    if licenca["hwid"] and licenca["hwid"] != req.hwid:
        registrar_log("activation_blocked", licenca["id"], f"HWID diferente: {req.hwid}", request.client.host)
        conn.close()
        raise HTTPException(status_code=403, detail="Licenca ja ativada em outro hardware.")
    
    if licenca["hwid"] == req.hwid and licenca["status"] == "active":
        if licenca["data_expiracao"]:
            data_exp = datetime.fromisoformat(licenca["data_expiracao"])
            if datetime.now() > data_exp:
                cursor.execute("UPDATE licencas SET status = 'expired' WHERE id = ?", (licenca["id"],))
                conn.commit()
                conn.close()
                raise HTTPException(status_code=403, detail="Licenca expirada.")
        conn.close()
        return APIResponse(status=True, mensagem="Licenca ja estava ativada.", dados={
            "key": licenca["key"], "plano": licenca["plano"],
            "expira_em": licenca["data_expiracao"], "tipo": PLANOS[licenca["plano"]]["tipo"]
        })
    
    data_expiracao = None
    if PLANOS[licenca["plano"]]["duracao_minutos"]:
        data_expiracao = (datetime.now() + timedelta(minutes=PLANOS[licenca["plano"]]["duracao_minutos"])).isoformat()
    
    cursor.execute(
        "UPDATE licencas SET hwid = ?, ativada_em = ?, status = 'active', data_expiracao = ? WHERE id = ?",
        (req.hwid, datetime.now().isoformat(), data_expiracao, licenca["id"])
    )
    conn.commit()
    conn.close()
    
    registrar_log("license_activated", licenca["id"], f"Ativada HWID: {req.hwid}", request.client.host)
    return APIResponse(status=True, mensagem="Licenca ativada com sucesso.", dados={
        "key": licenca["key"], "plano": licenca["plano"],
        "expira_em": data_expiracao, "tipo": PLANOS[licenca["plano"]]["tipo"]
    })

@app.post("/verify", response_model=APIResponse)
async def verify(request: Request, req: VerifyRequest, _: bool = Depends(rate_limit_middleware)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM licencas WHERE key = ?", (req.key,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        raise HTTPException(status_code=404, detail="Chave invalida.")
    
    licenca = {"id": result[0], "key": result[1], "plano": result[3], "status": result[4], "hwid": result[5], "data_expiracao": result[7]}
    
    if licenca["hwid"] != req.hwid:
        conn.close()
        raise HTTPException(status_code=403, detail="HWID nao corresponde.")
    if verificar_expiracao_licenca(licenca):
        conn.close()
        raise HTTPException(status_code=403, detail="Licenca expirada.")
    if licenca["status"] != "active":
        conn.close()
        raise HTTPException(status_code=403, detail="Licenca invalida.")
    
    cursor.execute("UPDATE licencas SET ultima_verificacao = ? WHERE id = ?", (datetime.now().isoformat(), licenca["id"]))
    conn.commit()
    conn.close()
    
    return APIResponse(status=True, mensagem="Licenca valida.", dados={
        "key": licenca["key"], "plano": licenca["plano"], "expira_em": licenca["data_expiracao"]
    })

@app.post("/heartbeat", response_model=APIResponse)
async def heartbeat(request: Request, req: HeartbeatRequest, _: bool = Depends(rate_limit_middleware)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM licencas WHERE key = ?", (req.key,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        raise HTTPException(status_code=404, detail="Chave invalida.")
    
    licenca = {"id": result[0], "key": result[1], "plano": result[3], "status": result[4], "hwid": result[5], "data_expiracao": result[7]}
    
    if licenca["hwid"] != req.hwid:
        conn.close()
        raise HTTPException(status_code=403, detail="HWID nao corresponde.")
    if verificar_expiracao_licenca(licenca):
        conn.close()
        raise HTTPException(status_code=403, detail="Licenca expirada.")
    
    cursor.execute("SELECT * FROM sessoes_ativas WHERE licenca_id = ? AND hwid = ?", (licenca["id"], req.hwid))
    sessao = cursor.fetchone()
    
    if not sessao:
        cursor.execute("INSERT INTO sessoes_ativas (id, licenca_id, hwid, key, iniciada_em, ultimo_heartbeat, heartbeats) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (str(uuid.uuid4()), licenca["id"], req.hwid, req.key, datetime.now().isoformat(), datetime.now().isoformat(), 1))
    else:
        cursor.execute("UPDATE sessoes_ativas SET ultimo_heartbeat = ?, heartbeats = heartbeats + 1 WHERE id = ?",
                       (datetime.now().isoformat(), sessao[0]))
    
    conn.commit()
    conn.close()
    
    return APIResponse(status=True, mensagem="Heartbeat recebido.", dados={"online": True})

# =========================================================
# ROTAS ADMIN - DASHBOARD
# =========================================================

@app.get("/admin/dashboard/stats", response_model=APIResponse)
async def admin_dashboard_stats(request: Request, _: dict = Depends(verify_admin_token), __: bool = Depends(rate_limit_middleware)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM licencas")
    total_licencas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT hwid) FROM licencas WHERE hwid IS NOT NULL")
    dispositivos_unicos = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE status = 'expired'")
    licencas_expiradas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE status = 'revoked'")
    licencas_revogadas = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE ativada_em IS NOT NULL")
    ativacoes_totais = cursor.fetchone()[0]
    
    taxa_ativacao = f"{(ativacoes_totais / total_licencas * 100):.1f}%" if total_licencas > 0 else "0%"
    
    hoje_fim = datetime.now().replace(hour=23, minute=59, second=59).isoformat()
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE data_expiracao IS NOT NULL AND data_expiracao <= ? AND status = 'active'", (hoje_fim,))
    expirando_hoje = cursor.fetchone()[0]
    
    em_7_dias = (datetime.now() + timedelta(days=7)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE data_expiracao IS NOT NULL AND data_expiracao <= ? AND data_expiracao > ? AND status = 'active'", (em_7_dias, hoje_fim))
    expirando_7dias = cursor.fetchone()[0]
    
    limite_24h = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute("SELECT COUNT(DISTINCT hwid) FROM licencas WHERE ultima_verificacao IS NOT NULL AND ultima_verificacao >= ?", (limite_24h,))
    ativos_24h = cursor.fetchone()[0] or 0
    
    limite_7d = (datetime.now() - timedelta(days=7)).isoformat()
    cursor.execute("SELECT COUNT(DISTINCT hwid) FROM licencas WHERE ultima_verificacao IS NOT NULL AND ultima_verificacao >= ?", (limite_7d,))
    ativos_7d = cursor.fetchone()[0] or 0
    
    limite_30d = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute("SELECT COUNT(DISTINCT hwid) FROM licencas WHERE ultima_verificacao IS NOT NULL AND ultima_verificacao >= ?", (limite_30d,))
    ativos_30d = cursor.fetchone()[0] or 0
    
    timeout_online = 90
    limite_online = (datetime.now() - timedelta(seconds=timeout_online)).isoformat()
    cursor.execute("SELECT COUNT(DISTINCT hwid) FROM sessoes_ativas WHERE ultimo_heartbeat > ?", (limite_online,))
    online_agora = cursor.fetchone()[0] or 0
    
    conn.close()
    
    return APIResponse(status=True, mensagem="Estatisticas carregadas", dados={
        "total_licencas": total_licencas,
        "dispositivos_unicos": dispositivos_unicos,
        "online_agora": online_agora,
        "licencas_expiradas": licencas_expiradas,
        "licencas_revogadas": licencas_revogadas,
        "ativacoes_totais": ativacoes_totais,
        "taxa_ativacao": taxa_ativacao,
        "expirando_hoje": expirando_hoje,
        "expirando_7dias": expirando_7dias,
        "ativos_24h": ativos_24h,
        "ativos_7d": ativos_7d,
        "ativos_30d": ativos_30d
    })

@app.get("/admin/dashboard/online", response_model=APIResponse)
async def admin_dashboard_online(request: Request, _: dict = Depends(verify_admin_token), __: bool = Depends(rate_limit_middleware)):
    conn = get_db()
    cursor = conn.cursor()
    
    timeout_online = 90
    limite_online = (datetime.now() - timedelta(seconds=timeout_online)).isoformat()
    
    cursor.execute("""
        SELECT s.hwid, s.key, s.ultimo_heartbeat, l.plano, l.produto_slug
        FROM sessoes_ativas s
        JOIN licencas l ON s.licenca_id = l.id
        WHERE s.ultimo_heartbeat > ?
        LIMIT 100
    """, (limite_online,))
    
    online = []
    for row in cursor.fetchall():
        online.append({
            "hwid": row[0][:20] + "..." if row[0] and len(row[0]) > 20 else row[0],
            "chave": f"{row[1][:4]}****{row[1][-4:]}" if row[1] else None,
            "ultimo_heartbeat": datetime.fromisoformat(row[2]).strftime("%d/%m/%Y %H:%M:%S"),
            "plano": row[3],
            "produto": row[4]
        })
    
    conn.close()
    
    return APIResponse(status=True, mensagem=f"{len(online)} usuarios online", dados={
        "online_agora": len(online),
        "usuarios": online
    })

@app.get("/admin/dashboard/users", response_model=APIResponse)
async def admin_dashboard_users(
    request: Request,
    page: int = 1,
    limit: int = 50,
    plano_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    _: dict = Depends(verify_admin_token), 
    __: bool = Depends(rate_limit_middleware)
):
    limit = min(limit, 100)
    page = max(page, 1)
    
    conn = get_db()
    cursor = conn.cursor()
    agora = datetime.now()
    
    query = """
        SELECT key, produto_slug, plano, status, hwid, ativada_em, 
               data_expiracao, criada_em, ultima_verificacao
        FROM licencas WHERE 1=1
    """
    params = []
    
    if plano_filter:
        query += " AND plano = ?"
        params.append(plano_filter)
    
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    
    cursor.execute(f"SELECT COUNT(*) FROM ({query})", params)
    total_usuarios = cursor.fetchone()[0]
    
    offset = (page - 1) * limit
    query += " ORDER BY CASE WHEN ultima_verificacao IS NULL THEN 1 ELSE 0 END, ultima_verificacao DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    
    cursor.execute(query, params)
    licencas = cursor.fetchall()
    
    timeout_online = 90
    limite_online = (datetime.now() - timedelta(seconds=timeout_online)).isoformat()
    cursor.execute("SELECT hwid FROM sessoes_ativas WHERE ultimo_heartbeat > ?", (limite_online,))
    online_hwids = {row[0] for row in cursor.fetchall()}
    
    conn.close()
    
    usuarios = []
    for lic in licencas:
        chave = lic[0]
        plano = lic[2]
        status = lic[3]
        hwid = lic[4]
        ativada_em = datetime.fromisoformat(lic[5]) if lic[5] else None
        data_expiracao = datetime.fromisoformat(lic[6]) if lic[6] else None
        ultima_verificacao = datetime.fromisoformat(lic[8]) if lic[8] else None
        
        esta_online = hwid in online_hwids if hwid else False
        
        dias_restantes = None
        tempo_restante_str = "Nunca ativada"
        
        if status == "revoked":
            tempo_restante_str = "Revogada"
        elif status == "expired":
            tempo_restante_str = "Expirada"
        elif data_expiracao:
            if data_expiracao > datetime.now():
                resto = data_expiracao - datetime.now()
                dias_restantes = resto.days
                if dias_restantes > 0:
                    tempo_restante_str = f"{dias_restantes} dias"
                elif resto.seconds // 3600 > 0:
                    tempo_restante_str = f"{resto.seconds // 3600} horas"
                else:
                    tempo_restante_str = f"{resto.seconds // 60} minutos"
            else:
                tempo_restante_str = "Expirada"
                dias_restantes = 0
        elif plano == "lifetime":
            tempo_restante_str = "Vitalicio"
            dias_restantes = -1
        
        ultimo_acesso = ultima_verificacao if ultima_verificacao else (ativada_em if ativada_em else None)
        ultimo_acesso_str = ultimo_acesso.strftime("%d/%m/%Y %H:%M:%S") if ultimo_acesso else "Nunca"
        
        chave_mascarada = f"{chave[:4]}****{chave[-4:]}" if len(chave) > 8 else "****"
        
        usuarios.append({
            "hwid": hwid[:20] + "..." if hwid and len(hwid) > 20 else (hwid if hwid else "Nao ativada"),
            "chave": chave_mascarada,
            "plano": plano,
            "status": status,
            "online": esta_online,
            "ativada_em": ativada_em.strftime("%d/%m/%Y %H:%M:%S") if ativada_em else "Nao ativada",
            "ultimo_acesso": ultimo_acesso_str,
            "dias_restantes": dias_restantes,
            "tempo_restante": tempo_restante_str
        })
    
    return APIResponse(status=True, mensagem="Usuarios carregados", dados={
        "usuarios": usuarios,
        "paginacao": {
            "pagina_atual": page,
            "limite": limit,
            "total_registros": total_usuarios,
            "total_paginas": (total_usuarios + limit - 1) // limit if total_usuarios > 0 else 1
        }
    })

@app.get("/admin/dashboard/plans", response_model=APIResponse)
async def admin_dashboard_plans(request: Request, _: dict = Depends(verify_admin_token), __: bool = Depends(rate_limit_middleware)):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT plano, COUNT(*) as total, 
               COUNT(DISTINCT CASE WHEN hwid IS NOT NULL THEN hwid END) as dispositivos,
               SUM(CASE WHEN hwid IS NOT NULL THEN 1 ELSE 0 END) as ativadas
        FROM licencas 
        GROUP BY plano
    """)
    
    planos = {}
    for row in cursor.fetchall():
        planos[row[0]] = {
            "total": row[1],
            "dispositivos_unicos": row[2] or 0,
            "ativadas": row[3],
            "taxa_ativacao": f"{(row[3] / row[1] * 100):.1f}%" if row[1] > 0 else "0%"
        }
    
    conn.close()
    
    return APIResponse(status=True, mensagem="Estatisticas por plano", dados=planos)

# =========================================================
# ROTAS ADMIN (LEGADO)
# =========================================================

@app.post("/admin/login", response_model=APIResponse)
async def admin_login(request: Request, req: AdminLoginRequest, _: bool = Depends(rate_limit_middleware)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admin_users WHERE username = ?", (req.username,))
    result = cursor.fetchone()
    
    if not result or not verify_password(req.password, result[2]):
        registrar_log("login_failed", "unknown", f"Falha login: {req.username}", request.client.host)
        conn.close()
        raise HTTPException(status_code=401, detail="Credenciais invalidas.")
    
    cursor.execute("UPDATE admin_users SET ultimo_login = ? WHERE id = ?", (datetime.now().isoformat(), result[0]))
    conn.commit()
    conn.close()
    
    token = jwt.encode({'user_id': result[0], 'username': result[1], 'role': 'admin', 'exp': datetime.now() + timedelta(seconds=JWT_EXPIRATION)}, SECRET_KEY, algorithm=JWT_ALGORITHM)
    registrar_log("login_success", result[0], f"Login: {req.username}", request.client.host)
    return APIResponse(status=True, mensagem="Login realizado com sucesso.", dados={"token": token, "expira_em": (datetime.now() + timedelta(seconds=JWT_EXPIRATION)).isoformat()})

@app.post("/admin/create-product", response_model=APIResponse)
async def admin_create_product(request: Request, req: CreateProductRequest, _: dict = Depends(verify_admin_token), __: bool = Depends(rate_limit_middleware)):
    slug = gerar_slug(req.nome)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM produtos WHERE slug = ?", (slug,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Produto ja existe.")
    
    produto_id = str(uuid.uuid4())
    cursor.execute("INSERT INTO produtos (id, nome, slug, descricao, criado_em) VALUES (?, ?, ?, ?, ?)", 
                   (produto_id, req.nome, slug, req.descricao, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    registrar_log("product_created", produto_id, f"Produto: {req.nome}", request.client.host)
    return APIResponse(status=True, mensagem="Produto criado com sucesso.", dados={"id": produto_id, "nome": req.nome, "slug": slug})

@app.post("/admin/create-license", response_model=APIResponse)
async def admin_create_license(request: Request, req: CreateLicenseRequest, _: dict = Depends(verify_admin_token), __: bool = Depends(rate_limit_middleware)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM produtos WHERE slug = ?", (req.produto_slug,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Produto nao encontrado.")
    
    if req.plano not in PLANOS:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Plano invalido. Opcoes: {list(PLANOS.keys())}")
    
    chave = gerar_chave_formatada()
    licenca_id = str(uuid.uuid4())
    cursor.execute("INSERT INTO licencas (id, key, produto_slug, plano, status, hwid, ativada_em, data_expiracao, criada_em, criada_por, ultima_verificacao) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                   (licenca_id, chave, req.produto_slug, req.plano, 'active', None, None, None, datetime.now().isoformat(), 'admin', None))
    conn.commit()
    conn.close()
    
    registrar_log("license_created", licenca_id, f"Licenca {req.plano} para {req.produto_slug}", request.client.host)
    return APIResponse(status=True, mensagem="Licenca criada com sucesso.", dados={"key": chave, "produto_slug": req.produto_slug, "plano": req.plano, "expira_em": "Ao ativar"})

@app.post("/admin/revoke-license", response_model=APIResponse)
async def admin_revoke_license(request: Request, req: RevokeLicenseRequest, _: dict = Depends(verify_admin_token), __: bool = Depends(rate_limit_middleware)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM licencas WHERE key = ?", (req.key,))
    licenca = cursor.fetchone()
    
    if not licenca:
        conn.close()
        raise HTTPException(status_code=404, detail="Licenca nao encontrada.")
    
    cursor.execute("UPDATE licencas SET status = 'revoked' WHERE key = ?", (req.key,))
    cursor.execute("DELETE FROM sessoes_ativas WHERE key = ?", (req.key,))
    conn.commit()
    conn.close()
    
    registrar_log("license_revoked", licenca[0], f"Revogada: {req.motivo}", request.client.host)
    return APIResponse(status=True, mensagem="Licenca revogada com sucesso.", dados={"key": req.key, "status": "revoked"})

@app.get("/admin/online-users", response_model=APIResponse)
async def admin_online_users(request: Request, _: dict = Depends(verify_admin_token), __: bool = Depends(rate_limit_middleware)):
    await limpar_sessoes_inativas()
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT s.key, s.hwid, s.ultimo_heartbeat, s.heartbeats, l.plano, l.produto_slug
        FROM sessoes_ativas s
        JOIN licencas l ON s.licenca_id = l.id
    """)
    sessoes = cursor.fetchall()
    conn.close()
    
    usuarios_online = []
    for sessao in sessoes:
        ultimo_heartbeat = datetime.fromisoformat(sessao[2])
        online_ha = (datetime.now() - ultimo_heartbeat).total_seconds()
        usuarios_online.append({"key": sessao[0], "hwid": sessao[1], "plano": sessao[4], "produto_slug": sessao[5], "online_ha": online_ha, "heartbeats": sessao[3]})
    
    return APIResponse(status=True, mensagem=f"Usuarios online: {len(usuarios_online)}", dados=usuarios_online)

@app.get("/admin/licenses", response_model=APIResponse)
async def admin_licenses(request: Request, produto_slug: Optional[str] = None, status: Optional[str] = None, plano: Optional[str] = None, _: dict = Depends(verify_admin_token), __: bool = Depends(rate_limit_middleware)):
    conn = get_db()
    cursor = conn.cursor()
    query = "SELECT key, produto_slug, plano, status, hwid, ativada_em, data_expiracao, criada_em FROM licencas WHERE 1=1"
    params = []
    
    if produto_slug:
        query += " AND produto_slug = ?"
        params.append(produto_slug)
    if status:
        query += " AND status = ?"
        params.append(status)
    if plano:
        query += " AND plano = ?"
        params.append(plano)
    
    cursor.execute(query, params)
    licencas_data = cursor.fetchall()
    conn.close()
    
    resultado = []
    for l in licencas_data:
        expira_texto = l[6] if l[6] else "Nao ativada"
        resultado.append({
            "key": l[0], "produto_slug": l[1], "plano": l[2], "status": l[3],
            "hwid": l[4] if l[4] else "Nao ativada", "ativada_em": l[5] if l[5] else "Aguardando ativacao",
            "expira_em": expira_texto, "criada_em": l[7]
        })
    return APIResponse(status=True, mensagem=f"Licencas encontradas: {len(resultado)}", dados=resultado)

@app.get("/admin/stats", response_model=APIResponse)
async def admin_stats(request: Request, _: dict = Depends(verify_admin_token), __: bool = Depends(rate_limit_middleware)):
    await limpar_sessoes_inativas()
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM licencas")
    total_licencas = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE status = 'active'")
    licencas_ativas = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE status = 'expired'")
    licencas_expiradas = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE status = 'revoked'")
    licencas_revogadas = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM sessoes_ativas")
    usuarios_online = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM produtos")
    total_produtos = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM licencas WHERE hwid IS NULL AND status = 'active'")
    nao_ativadas = cursor.fetchone()[0]
    
    stats_por_plano = {}
    for plano in PLANOS.keys():
        cursor.execute("SELECT COUNT(*) FROM licencas WHERE plano = ?", (plano,))
        stats_por_plano[plano] = cursor.fetchone()[0]
    
    cursor.execute("SELECT acao, detalhes, timestamp FROM logs ORDER BY timestamp DESC LIMIT 20")
    ultimos_logs = [{"acao": l[0], "detalhes": l[1], "timestamp": l[2]} for l in cursor.fetchall()]
    
    conn.close()
    
    stats = {"total_licencas": total_licencas, "licencas_ativas": licencas_ativas, "licencas_nao_ativadas": nao_ativadas,
             "licencas_expiradas": licencas_expiradas, "licencas_revogadas": licencas_revogadas,
             "usuarios_online": usuarios_online, "produtos": total_produtos, "por_plano": stats_por_plano, "ultimos_logs": ultimos_logs}
    return APIResponse(status=True, mensagem="Estatisticas do sistema", dados=stats)

# =========================================================
# INICIAR API
# =========================================================

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("LICENSE SERVER API v4.0 - PROFISSIONAL")
    print("=" * 60)
    print("\nAPI rodando em http://localhost:5000")
    print("Documentacao: http://localhost:5000/docs")
    print("\nSenha admin: 36791788")
    print("\nPLANOS DISPONIVEIS:")
    for plano, info in PLANOS.items():
        duracao = f"{info['duracao_minutos']} minutos" if info['duracao_minutos'] else "Vitalicio"
        print(f"  - {plano}: {info['nome']} ({duracao})")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=5000, reload=False)