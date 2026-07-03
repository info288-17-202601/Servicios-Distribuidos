"""
Modelos SQLAlchemy compartidos entre microservicios.
Cada servicio importa solo lo que necesita.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, Text,
    DateTime, ForeignKey, Float, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Admin(Base):
    __tablename__ = "admins"

    id           = Column(Integer, primary_key=True)
    username     = Column(String(80),  nullable=False, unique=True)
    email        = Column(String(120), nullable=False, unique=True)
    password_hash = Column(Text,       nullable=False)
    created_at   = Column(DateTime,    default=datetime.utcnow)


class Client(Base):
    __tablename__ = "clients"

    id         = Column(Integer,     primary_key=True)
    name       = Column(String(100), nullable=False)
    email      = Column(String(120), nullable=False, unique=True)
    api_key    = Column(String(64),  nullable=False, unique=True)
    machine_id = Column(String(128))
    cert_subject = Column(String, nullable=True)
    is_active  = Column(Boolean,     default=True)
    created_at = Column(DateTime,    default=datetime.utcnow)

    permissions = relationship("ClientServicePermission", back_populates="client")
    logs        = relationship("UsageLog",                back_populates="client")


class Service(Base):
    __tablename__ = "services"

    id          = Column(Integer,     primary_key=True)
    name        = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    endpoint    = Column(String(255), nullable=False)
    method      = Column(String(10),  default="GET")
    is_active   = Column(Boolean,     default=True)
    timeout_sec = Column(Integer,     default=10)
    created_at  = Column(DateTime,    default=datetime.utcnow)
    updated_at  = Column(DateTime,    default=datetime.utcnow, onupdate=datetime.utcnow)

    permissions = relationship("ClientServicePermission", back_populates="service")
    logs        = relationship("UsageLog",                back_populates="service")
    metrics     = relationship("MetricsHourly",           back_populates="service")


class ClientServicePermission(Base):
    __tablename__ = "client_service_permissions"
    __table_args__ = (UniqueConstraint("client_id", "service_id"),)

    id         = Column(Integer,  primary_key=True)
    client_id  = Column(Integer,  ForeignKey("clients.id",  ondelete="CASCADE"))
    service_id = Column(Integer,  ForeignKey("services.id", ondelete="CASCADE"))
    granted_at = Column(DateTime, default=datetime.utcnow)

    client  = relationship("Client",  back_populates="permissions")
    service = relationship("Service", back_populates="permissions")


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id               = Column(Integer,    primary_key=True)
    client_id        = Column(Integer,    ForeignKey("clients.id",  ondelete="SET NULL"), nullable=True)
    service_id       = Column(Integer,    ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    gateway_instance = Column(String(50))
    request_method   = Column(String(10))
    status_code      = Column(Integer)
    response_time_ms = Column(Integer)
    client_ip        = Column(String(50))
    requested_at     = Column(DateTime,   default=datetime.utcnow)

    client  = relationship("Client",  back_populates="logs")
    service = relationship("Service", back_populates="logs")


class MetricsHourly(Base):
    __tablename__ = "metrics_hourly"
    __table_args__ = (UniqueConstraint("service_id", "hour_bucket"),)

    id              = Column(Integer,   primary_key=True)
    service_id      = Column(Integer,   ForeignKey("services.id", ondelete="CASCADE"))
    hour_bucket     = Column(DateTime,  nullable=False)
    total_requests  = Column(Integer,   default=0)
    success_count   = Column(Integer,   default=0)
    error_count     = Column(Integer,   default=0)
    avg_response_ms = Column(Float,     default=0.0)

    service = relationship("Service", back_populates="metrics")
