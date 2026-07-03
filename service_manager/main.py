"""
Service Manager — Microservicio de administración de servicios y clientes.

Funcionalidades:
  • CRUD completo de servicios registrados (endpoints)
  • CRUD de clientes
  • Gestión de permisos cliente↔servicio
  • Activar / desactivar servicios sin reiniciar el gateway
"""
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from jose import jwt
from passlib.context import CryptContext
from datetime import timedelta

sys.path.insert(0, "/app")
from shared.database import get_db, init_db
from shared.models import (
    Admin,
    Client,
    Service,
    ClientServicePermission
)

from fastapi.security import HTTPBearer
from fastapi.security import HTTPAuthorizationCredentials

security = HTTPBearer()

SECRET_KEY = "change_this_secret_key"

ALGORITHM = "HS256"

ACCESS_TOKEN_EXPIRE_MINUTES = 480

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

class LoginAdmin(BaseModel):

    username: str

    password: str


class LoginClient(BaseModel):

    email: str

    api_key: str


class ClientUpdate(BaseModel):

    name: str | None = None

    email: str | None = None

    api_key: str | None = None

    machine_id: str | None = None

    is_active: bool | None = None

# Schemas Pydantic

class ServiceCreate(BaseModel):
    name:        str
    description: str | None = None
    endpoint:    str
    method:      str = "GET"
    timeout_sec: int = 10
    is_active:   bool = True


class ServiceUpdate(BaseModel):
    description: str | None = None
    endpoint:    str | None = None
    method:      str | None = None
    timeout_sec: int | None = None
    is_active:   bool | None = None


class ClientCreate(BaseModel):
    name:       str
    email:      str
    api_key:    str
    machine_id: str | None = None


class PermissionGrant(BaseModel):
    client_id:  int
    service_id: int

# App

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Service Manager",
    description="Administración de servicios y clientes del sistema distribuido",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Health

@app.get("/health")
async def health():
    return {"status": "ok", "service": "service_manager", "timestamp": datetime.utcnow().isoformat()}

# Gestión de Servicios

@app.get("/services")
async def list_services(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Service).order_by(Service.id))
    services = result.scalars().all()
    return [
        {
            "id": s.id, "name": s.name, "description": s.description,
            "endpoint": s.endpoint, "method": s.method,
            "is_active": s.is_active, "timeout_sec": s.timeout_sec,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in services
    ]


@app.get("/services/{service_id}")
async def get_service(service_id: int, db: AsyncSession = Depends(get_db)):
    s = await db.get(Service, service_id)
    if not s:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    return {"id": s.id, "name": s.name, "description": s.description,
            "endpoint": s.endpoint, "method": s.method, "is_active": s.is_active}


@app.post("/services", status_code=201)
async def create_service(body: ServiceCreate, db: AsyncSession = Depends(get_db)):
    # Verificar duplicado
    existing = await db.execute(select(Service).where(Service.name == body.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Ya existe un servicio llamado '{body.name}'")

    svc = Service(**body.model_dump())
    db.add(svc)
    await db.commit()
    await db.refresh(svc)
    return {"id": svc.id, "name": svc.name, "message": "Servicio creado"}


@app.put("/services/{service_id}")
async def update_service(service_id: int, body: ServiceUpdate, db: AsyncSession = Depends(get_db)):
    svc = await db.get(Service, service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(svc, field, value)
    svc.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Servicio actualizado", "id": service_id}


@app.delete("/services/{service_id}", status_code=204)
async def delete_service(service_id: int, db: AsyncSession = Depends(get_db)):
    svc = await db.get(Service, service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    await db.delete(svc)
    await db.commit()


@app.patch("/services/{service_id}/toggle")
async def toggle_service(service_id: int, db: AsyncSession = Depends(get_db)):
    """Activa o desactiva un servicio en caliente (sin reiniciar gateway)."""
    svc = await db.get(Service, service_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Servicio no encontrado")
    svc.is_active  = not svc.is_active
    svc.updated_at = datetime.utcnow()
    await db.commit()
    return {"id": service_id, "is_active": svc.is_active, "message": f"Servicio {'activado' if svc.is_active else 'desactivado'}"}


# Gestión de Clientes

@app.get("/clients")
async def list_clients(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Client).order_by(Client.id))
    clients = result.scalars().all()
    return [
        {
            "id": c.id, "name": c.name, "email": c.email,
            "api_key": c.api_key, "is_active": c.is_active,
            "machine_id": c.machine_id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in clients
    ]


@app.post("/clients", status_code=201)
async def create_client(body: ClientCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(Client).where(Client.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe un cliente con ese email")

    client = Client(**body.model_dump())
    db.add(client)
    await db.commit()
    await db.refresh(client)
    return {"id": client.id, "name": client.name, "api_key": client.api_key}


@app.patch("/clients/{client_id}/toggle")
async def toggle_client(client_id: int, db: AsyncSession = Depends(get_db)):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    client.is_active = not client.is_active
    await db.commit()
    return {"id": client_id, "is_active": client.is_active}


@app.delete("/clients/{client_id}", status_code=204)
async def delete_client(client_id: int, db: AsyncSession = Depends(get_db)):
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    await db.delete(client)
    await db.commit()


# Gestión de Permisos

@app.get("/permissions/client/{client_id}")
async def get_client_permissions(client_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ClientServicePermission, Service)
        .join(Service, ClientServicePermission.service_id == Service.id)
        .where(ClientServicePermission.client_id == client_id)
    )
    rows = result.all()
    return [
        {"service_id": svc.id, "service_name": svc.name, "is_active": svc.is_active,
         "granted_at": perm.granted_at.isoformat() if perm.granted_at else None}
        for perm, svc in rows
    ]


@app.post("/permissions", status_code=201)
async def grant_permission(body: PermissionGrant, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(
        select(ClientServicePermission).where(
            ClientServicePermission.client_id  == body.client_id,
            ClientServicePermission.service_id == body.service_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="El permiso ya existe")
    perm = ClientServicePermission(client_id=body.client_id, service_id=body.service_id)
    db.add(perm)
    await db.commit()
    return {"message": "Permiso otorgado"}


@app.delete("/permissions")
async def revoke_permission(body: PermissionGrant, db: AsyncSession = Depends(get_db)):
    await db.execute(
        delete(ClientServicePermission).where(
            ClientServicePermission.client_id  == body.client_id,
            ClientServicePermission.service_id == body.service_id,
        )
    )
    await db.commit()
    return {"message": "Permiso revocado"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=os.getenv("SERVICE_HOST", "0.0.0.0"),
                port=int(os.getenv("SERVICE_PORT", 8001)), reload=False)

def create_token(data: dict):

    payload = data.copy()

    expire = datetime.utcnow() + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload["exp"] = expire

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

@app.post("/login")
async def login_admin(
    body: LoginAdmin,
    db: AsyncSession = Depends(get_db)
):

    result = await db.execute(
        select(Admin).where(
            Admin.username == body.username
        )
    )

    admin = result.scalar_one_or_none()

    if not admin:

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    if not pwd_context.verify(
        body.password,
        admin.password_hash
    ):

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    token = create_token({

        "sub": admin.username,

        "role": "admin"

    })

    return {

        "token": token,

        "username": admin.username

    }

@app.post("/client/login")
async def login_client(
    body: LoginClient,
    db: AsyncSession = Depends(get_db)
):

    result = await db.execute(
        select(Client).where(
            Client.email == body.email,
            Client.api_key == body.api_key
        )
    )

    client = result.scalar_one_or_none()

    if not client:

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    if not client.is_active:

        raise HTTPException(
            status_code=403,
            detail="Client disabled"
        )

    token = create_token({

        "sub": client.email,

        "role": "client",

        "client_id": client.id

    })

    return {

        "token": token,

        "client_id": client.id,

        "name": client.name

    }

@app.get("/clients/{client_id}")
async def get_client(

    client_id: int,

    db: AsyncSession = Depends(get_db)

):

    client = await db.get(
        Client,
        client_id
    )

    if not client:

        raise HTTPException(
            status_code=404,
            detail="Client not found"
        )

    return {

        "id": client.id,

        "name": client.name,

        "email": client.email,

        "api_key": client.api_key,

        "machine_id": client.machine_id,

        "is_active": client.is_active

    }

@app.put("/clients/{client_id}")
async def update_client(

    client_id: int,

    body: ClientUpdate,

    db: AsyncSession = Depends(get_db)

):

    client = await db.get(
        Client,
        client_id
    )

    if not client:

        raise HTTPException(
            status_code=404,
            detail="Client not found"
        )

    values = body.model_dump(
        exclude_none=True
    )

    for key, value in values.items():

        setattr(client, key, value)

    await db.commit()

    await db.refresh(client)

    return {

        "message": "Client updated",

        "id": client.id

    }

async def get_current_user(

    credentials: HTTPAuthorizationCredentials = Depends(security)

):

    try:

        return jwt.decode(

            credentials.credentials,

            SECRET_KEY,

            algorithms=[ALGORITHM]

        )

    except:

        raise HTTPException(

            status_code=401,

            detail="Invalid token"

        )
    
@app.get("/me")
async def me(

    user = Depends(get_current_user)

):

    return user