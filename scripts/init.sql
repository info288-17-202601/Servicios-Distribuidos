-- ============================================================
-- Esquema de base de datos — Sistema Distribuido
-- ============================================================

-- Tabla de administradores del sistema
CREATE TABLE IF NOT EXISTS admins (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(80)  NOT NULL UNIQUE,
    email       VARCHAR(120) NOT NULL UNIQUE,
    password_hash TEXT       NOT NULL,
    created_at  TIMESTAMP    DEFAULT NOW()
);

-- Tabla de clientes (consumidores de servicios)
CREATE TABLE IF NOT EXISTS clients (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(120) NOT NULL UNIQUE,
    api_key     VARCHAR(64)  NOT NULL UNIQUE,
    machine_id  VARCHAR(128),          -- identificador de la máquina registrada
    cert_subject VARCHAR(128),
    is_active   BOOLEAN      DEFAULT TRUE,
    created_at  TIMESTAMP    DEFAULT NOW()
);

-- Tabla de servicios registrados (endpoints administrables)
CREATE TABLE IF NOT EXISTS services (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    endpoint    VARCHAR(255) NOT NULL,  -- URL del servicio externo/interno
    method      VARCHAR(10)  DEFAULT 'GET',
    is_active   BOOLEAN      DEFAULT TRUE,
    timeout_sec INTEGER      DEFAULT 10,
    created_at  TIMESTAMP    DEFAULT NOW(),
    updated_at  TIMESTAMP    DEFAULT NOW()
);

-- Tabla de permisos: qué clientes pueden usar qué servicios
CREATE TABLE IF NOT EXISTS client_service_permissions (
    id          SERIAL PRIMARY KEY,
    client_id   INTEGER REFERENCES clients(id) ON DELETE CASCADE,
    service_id  INTEGER REFERENCES services(id) ON DELETE CASCADE,
    granted_at  TIMESTAMP DEFAULT NOW(),
    UNIQUE(client_id, service_id)
);

-- Tabla de métricas / log de uso
CREATE TABLE IF NOT EXISTS usage_logs (
    id            SERIAL PRIMARY KEY,
    client_id     INTEGER REFERENCES clients(id) ON DELETE SET NULL,
    service_id    INTEGER REFERENCES services(id) ON DELETE SET NULL,
    gateway_instance VARCHAR(50),
    request_method   VARCHAR(10),
    status_code      INTEGER,
    response_time_ms INTEGER,
    client_ip        VARCHAR(50),
    requested_at     TIMESTAMP DEFAULT NOW()
);

-- Tabla de métricas agregadas (para dashboard de monitoreo)
CREATE TABLE IF NOT EXISTS metrics_hourly (
    id            SERIAL PRIMARY KEY,
    service_id    INTEGER REFERENCES services(id) ON DELETE CASCADE,
    hour_bucket   TIMESTAMP NOT NULL,
    total_requests INTEGER  DEFAULT 0,
    success_count  INTEGER  DEFAULT 0,
    error_count    INTEGER  DEFAULT 0,
    avg_response_ms FLOAT   DEFAULT 0,
    UNIQUE(service_id, hour_bucket)
);

-- ──────────────────────────────────────────────────────────
-- Datos iniciales de ejemplo
-- ──────────────────────────────────────────────────────────

-- Servicios de ejemplo expuestos por el gateway
INSERT INTO services (name, description, endpoint, method, is_active) VALUES
    ('weather',       'Consulta clima por ciudad',       'https://wttr.in/{city}?format=j1',           'GET',  TRUE),
    ('quotes',        'Frases aleatorias motivacionales','https://dummyjson.com/quotes/random',         'GET',  TRUE),
    ('ip_info',       'Información de IP pública',       'https://httpbin.org/ip',                     'GET',  TRUE),
    ('user_agent',    'Devuelve el user-agent del req',  'https://httpbin.org/user-agent',             'GET',  TRUE),
    ('echo',          'Eco del request (prueba interna)','https://httpbin.org/anything',               'POST', TRUE)
ON CONFLICT (name) DO NOTHING;

-- Cliente de prueba (api_key = "testclient-key-001")
INSERT INTO clients (name, email, api_key, is_active) VALUES
    ('Cliente Demo',   'demo@example.com',   'testclient-key-001', TRUE),
    ('Cliente Demo 2', 'demo2@example.com',  'testclient-key-002', TRUE)
ON CONFLICT (email) DO NOTHING;

-- Permisos por defecto: Demo puede usar todos los servicios
INSERT INTO client_service_permissions (client_id, service_id)
SELECT c.id, s.id
FROM clients c, services s
WHERE c.email = 'demo@example.com'
ON CONFLICT DO NOTHING;

-- Demo2 solo puede usar quotes e ip_info
INSERT INTO client_service_permissions (client_id, service_id)
SELECT c.id, s.id
FROM clients c, services s
WHERE c.email = 'demo2@example.com' AND s.name IN ('quotes', 'ip_info')
ON CONFLICT DO NOTHING;

INSERT INTO admins
(
    username,
    email,
    password_hash
)
VALUES
(
    'admin',
    'admin@test.com',
    '$2b$12$6hPiYlSxPmyvYj0gKnM4IuGqUvvH0nUQHnYzO4VYV5T4Xh1nQ6PKe'
)
ON CONFLICT(username)
DO NOTHING;