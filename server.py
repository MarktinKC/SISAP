import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "ambulance.db"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
APP_ENV = os.getenv("APP_ENV", "development").lower()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SESSION_COOKIE = "ambulance_session"
SECRET_KEY = os.getenv("SECRET_KEY", "local-dev-secret-change-me")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
CAPACITY_LIMIT = 17
SESSION_DAYS = 7

STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


class Database:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = "postgres" if database_url else "sqlite"
        self.placeholder = "%s" if self.engine == "postgres" else "?"
        if self.engine == "postgres" and psycopg is None:
            raise RuntimeError("DATABASE_URL esta configurado pero falta instalar psycopg.")

    def connect(self):
        if self.engine == "postgres":
            return psycopg.connect(self.database_url, row_factory=dict_row)
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        return connection

    def query(self, sql: str) -> str:
        return sql.replace("{p}", self.placeholder)

    def fetchone(self, sql: str, params=()):
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(self.query(sql), params)
            row = cursor.fetchone()
            cursor.close()
            if row is None:
                return None
            return dict(row) if self.engine == "postgres" else dict(row)

    def fetchall(self, sql: str, params=()):
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(self.query(sql), params)
            rows = cursor.fetchall()
            cursor.close()
            return [dict(row) for row in rows]

    def execute(self, sql: str, params=(), *, fetchone=False):
        with self.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(self.query(sql), params)
            row = cursor.fetchone() if fetchone else None
            connection.commit()
            cursor.close()
            if row is None:
                return None
            return dict(row) if self.engine == "postgres" else dict(row)

    def exec_script(self, statements: list[str]):
        with self.connect() as connection:
            cursor = connection.cursor()
            for statement in statements:
                cursor.execute(statement)
            connection.commit()
            cursor.close()


db = Database(DATABASE_URL)


def utc_now() -> datetime:
    return datetime.now(UTC)


def now_iso() -> str:
    return utc_now().isoformat()


def to_b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def from_b64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def sign_value(value: bytes) -> str:
    return to_b64url(hmac.new(SECRET_KEY.encode("utf-8"), value, hashlib.sha256).digest())


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    salt_b64, digest_b64 = stored_hash.split("$", 1)
    salt = base64.b64decode(salt_b64.encode("utf-8"))
    expected = base64.b64decode(digest_b64.encode("utf-8"))
    calculated = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return hmac.compare_digest(expected, calculated)


def serialize_session(user: dict) -> str:
    payload = {
        "id": user["id"],
        "username": user["username"],
        "fullName": user["fullName"],
        "role": user["role"],
        "exp": int((utc_now() + timedelta(days=SESSION_DAYS)).timestamp()),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded_payload = to_b64url(payload_bytes)
    signature = sign_value(payload_bytes)
    return f"{encoded_payload}.{signature}"


def parse_session(token: str | None):
    if not token or "." not in token:
        return None
    encoded_payload, signature = token.rsplit(".", 1)
    payload_bytes = from_b64url(encoded_payload)
    expected_signature = sign_value(payload_bytes)
    if not hmac.compare_digest(signature, expected_signature):
        return None
    payload = json.loads(payload_bytes.decode("utf-8"))
    if int(payload.get("exp", 0)) < int(utc_now().timestamp()):
        return None
    return {
        "id": payload["id"],
        "username": payload["username"],
        "fullName": payload["fullName"],
        "role": payload["role"],
    }


def cookie_header(value: str, max_age: int | None = None) -> str:
    parts = [f"{SESSION_COOKIE}={value}", "HttpOnly", "Path=/", "SameSite=Lax"]
    if COOKIE_SECURE:
        parts.append("Secure")
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    return "; ".join(parts)


def init_db():
    if db.engine == "postgres":
        db.exec_script(
            [
                """
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    username TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'coordinador',
                    created_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS trips (
                    id BIGSERIAL PRIMARY KEY,
                    request_id TEXT NOT NULL UNIQUE,
                    passenger_name TEXT NOT NULL,
                    residencia TEXT NOT NULL,
                    companion_name TEXT,
                    destination TEXT NOT NULL,
                    trip_date TEXT NOT NULL,
                    trip_time TEXT NOT NULL,
                    driver_name TEXT NOT NULL,
                    unit_number TEXT NOT NULL,
                    contact_phone TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    created_by BIGINT NOT NULL REFERENCES users(id),
                    created_by_name TEXT NOT NULL
                )
                """,
            ]
        )
    else:
        db.exec_script(
            [
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    full_name TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'coordinador',
                    created_at TEXT NOT NULL
                )
                """,
                """
                CREATE TABLE IF NOT EXISTS trips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL UNIQUE,
                    passenger_name TEXT NOT NULL,
                    residencia TEXT NOT NULL,
                    companion_name TEXT,
                    destination TEXT NOT NULL,
                    trip_date TEXT NOT NULL,
                    trip_time TEXT NOT NULL,
                    driver_name TEXT NOT NULL,
                    unit_number TEXT NOT NULL,
                    contact_phone TEXT NOT NULL,
                    notes TEXT,
                    created_at TEXT NOT NULL,
                    created_by INTEGER NOT NULL REFERENCES users(id),
                    created_by_name TEXT NOT NULL
                )
                """,
            ]
        )

    user_count = db.fetchone("SELECT COUNT(*) AS total FROM users")
    if not user_count or user_count["total"] != 0:
        return

    admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
    admin_username = os.getenv("ADMIN_USERNAME", "admin").strip().lower()
    admin_full_name = os.getenv("ADMIN_FULL_NAME", "Coordinacion de Traslados").strip()

    if APP_ENV == "production" and not admin_password:
        return

    if not admin_password:
        admin_password = "admin123"

    db.execute(
        """
        INSERT INTO users (username, full_name, password_hash, role, created_at)
        VALUES ({p}, {p}, {p}, {p}, {p})
        """,
        (admin_username, admin_full_name, hash_password(admin_password), "administrador", now_iso()),
    )


class AmbulanceHandler(BaseHTTPRequestHandler):
    server_version = "AmbulanceApp/2.0"

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.handle_api_get(parsed.path)
            return
        self.serve_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.respond_json({"error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)
            return
        self.handle_api_post(parsed.path)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            self.respond_json({"error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)
            return
        self.handle_api_delete(parsed.path)

    def handle_api_get(self, path: str):
        if path == "/api/health":
            self.respond_json({"ok": True, "database": db.engine})
            return

        if path == "/api/auth/session":
            user = self.require_user()
            if not user:
                return
            self.respond_json({"user": user})
            return

        if path == "/api/trips":
            user = self.require_user()
            if not user:
                return
            records = db.fetchall(
                """
                SELECT id, request_id, passenger_name, residencia, companion_name,
                       destination, trip_date, trip_time, driver_name, unit_number,
                       contact_phone, notes, created_at, created_by_name
                FROM trips
                ORDER BY trip_date ASC, trip_time ASC, id ASC
                """
            )
            self.respond_json({"records": records, "capacityLimit": CAPACITY_LIMIT})
            return

        self.respond_json({"error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)

    def handle_api_post(self, path: str):
        data = self.read_json_body()
        if data is None:
            return

        if path == "/api/auth/login":
            self.login(data)
            return

        if path == "/api/auth/register":
            self.register(data)
            return

        if path == "/api/auth/logout":
            self.logout()
            return

        if path == "/api/trips":
            user = self.require_user()
            if not user:
                return
            self.create_trip(data, user)
            return

        self.respond_json({"error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)

    def handle_api_delete(self, path: str):
        user = self.require_user()
        if not user:
            return

        if user.get("role") != "administrador":
            self.respond_json(
                {"error": "Solo el administrador puede eliminar registros."},
                HTTPStatus.FORBIDDEN,
            )
            return

        if path.startswith("/api/trips/"):
            trip_id = path.rsplit("/", 1)[-1]
            deleted = db.execute(
                "DELETE FROM trips WHERE id = {p} RETURNING id" if db.engine == "postgres" else "DELETE FROM trips WHERE id = {p}",
                (trip_id,),
                fetchone=(db.engine == "postgres"),
            )
            if db.engine == "postgres":
                if not deleted:
                    self.respond_json({"error": "Registro no encontrado."}, HTTPStatus.NOT_FOUND)
                    return
            else:
                remaining = db.fetchone("SELECT id FROM trips WHERE id = {p}", (trip_id,))
                if remaining:
                    self.respond_json({"error": "No fue posible eliminar el registro."}, HTTPStatus.CONFLICT)
                    return
            self.respond_json({"ok": True})
            return

        self.respond_json({"error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)

    def login(self, data: dict):
        username = (data.get("username") or "").strip().lower()
        password = data.get("password") or ""
        if not username or not password:
            self.respond_json({"error": "Completa usuario y contrasena."}, HTTPStatus.BAD_REQUEST)
            return

        user = db.fetchone(
            "SELECT id, username, full_name, password_hash, role FROM users WHERE username = {p}",
            (username,),
        )
        if not user or not verify_password(password, user["password_hash"]):
            self.respond_json({"error": "Usuario o contrasena incorrectos."}, HTTPStatus.UNAUTHORIZED)
            return

        public_user = {
            "id": user["id"],
            "username": user["username"],
            "fullName": user["full_name"],
            "role": user["role"],
        }
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", cookie_header(serialize_session(public_user), SESSION_DAYS * 24 * 60 * 60))
        self.end_headers()
        self.wfile.write(json.dumps({"user": public_user}).encode("utf-8"))

    def register(self, data: dict):
        username = (data.get("username") or "").strip().lower()
        full_name = (data.get("fullName") or "").strip()
        password = data.get("password") or ""

        if len(username) < 4 or len(password) < 6 or len(full_name) < 4:
            self.respond_json({"error": "Completa nombre, usuario y contrasena valida."}, HTTPStatus.BAD_REQUEST)
            return

        existing = db.fetchone("SELECT id FROM users WHERE username = {p}", (username,))
        if existing:
            self.respond_json({"error": "El usuario ya existe."}, HTTPStatus.CONFLICT)
            return

        created = db.execute(
            """
            INSERT INTO users (username, full_name, password_hash, role, created_at)
            VALUES ({p}, {p}, {p}, {p}, {p})
            RETURNING id
            """ if db.engine == "postgres" else
            """
            INSERT INTO users (username, full_name, password_hash, role, created_at)
            VALUES ({p}, {p}, {p}, {p}, {p})
            """,
            (username, full_name, hash_password(password), "coordinador", now_iso()),
            fetchone=(db.engine == "postgres"),
        )

        if db.engine == "postgres":
            user_id = created["id"]
        else:
            user_id_row = db.fetchone("SELECT id FROM users WHERE username = {p}", (username,))
            user_id = user_id_row["id"]

        public_user = {
            "id": user_id,
            "username": username,
            "fullName": full_name,
            "role": "coordinador",
        }
        self.send_response(HTTPStatus.CREATED)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", cookie_header(serialize_session(public_user), SESSION_DAYS * 24 * 60 * 60))
        self.end_headers()
        self.wfile.write(json.dumps({"user": public_user}).encode("utf-8"))

    def logout(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Set-Cookie", cookie_header("", 0))
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def create_trip(self, data: dict, user: dict):
        record = {
            "request_id": (data.get("requestId") or "").strip(),
            "passenger_name": (data.get("passengerName") or "").strip(),
            "residencia": data.get("residence").strip(),
            "companion_name": (data.get("companionName") or "").strip(),
            "destination": (data.get("destination") or "").strip(),
            "trip_date": (data.get("tripDate") or "").strip(),
            "trip_time": (data.get("tripTime") or "").strip(),
            "driver_name": (data.get("driverName") or "").strip(),
            "unit_number": (data.get("unitNumber") or "").strip(),
            "contact_phone": (data.get("contactPhone") or "").strip(),
            "notes": (data.get("notes") or "").strip(),
        }

        required = [
            "request_id",
            "passenger_name",
            "residencia",
            "destination",
            "trip_date",
            "trip_time",
            "driver_name",
            "unit_number",
            "contact_phone",
        ]
        if any(not record[field] for field in required):
            self.respond_json({"error": "Completa todos los campos obligatorios."}, HTTPStatus.BAD_REQUEST)
            return

        

        occupancy = db.fetchone(
            """
            SELECT COUNT(*) AS total
            FROM trips
            WHERE destination = {p} AND trip_date = {p} AND trip_time = {p}
            """,
            (record["destination"], record["trip_date"], record["trip_time"]),
        )["total"]
        if occupancy >= CAPACITY_LIMIT:
            self.respond_json({"error": "Este viaje ya alcanzo el limite de 17 personas."}, HTTPStatus.CONFLICT)
            return

        existing = db.fetchone("SELECT id FROM trips WHERE request_id = {p}", (record["request_id"],))
        if existing:
            self.respond_json({"error": "El folio de solicitud ya existe."}, HTTPStatus.CONFLICT)
            return

        created_at = now_iso()
        inserted = db.execute(
            """
            INSERT INTO trips (
                request_id, passenger_name, residencia, companion_name, destination,
                trip_date, trip_time, driver_name, unit_number, contact_phone, notes,
                created_at, created_by, created_by_name
            ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            RETURNING id
            """ if db.engine == "postgres" else
            """
            INSERT INTO trips (
                request_id, passenger_name, residencia, companion_name, destination,
                trip_date, trip_time, driver_name, unit_number, contact_phone, notes,
                created_at, created_by, created_by_name
            ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            """,
            (
                record["request_id"],
                record["passenger_name"],
                record["residencia"],
                record["companion_name"],
                record["destination"],
                record["trip_date"],
                record["trip_time"],
                record["driver_name"],
                record["unit_number"],
                record["contact_phone"],
                record["notes"],
                created_at,
                user["id"],
                user["fullName"],
            ),
            fetchone=(db.engine == "postgres"),
        )

        if db.engine == "postgres":
            trip_id = inserted["id"]
        else:
            trip_row = db.fetchone("SELECT id FROM trips WHERE request_id = {p}", (record["request_id"],))
            trip_id = trip_row["id"]

        created_record = {
            "id": trip_id,
            "request_id": record["request_id"],
            "passenger_name": record["passenger_name"],
            "residencia": record["residencia"],
            "companion_name": record["companion_name"],
            "destination": record["destination"],
            "trip_date": record["trip_date"],
            "trip_time": record["trip_time"],
            "driver_name": record["driver_name"],
            "unit_number": record["unit_number"],
            "contact_phone": record["contact_phone"],
            "notes": record["notes"],
            "created_at": created_at,
            "created_by_name": user["fullName"],
        }
        self.respond_json({"record": created_record, "occupancy": occupancy + 1}, HTTPStatus.CREATED)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            return json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self.respond_json({"error": "JSON invalido."}, HTTPStatus.BAD_REQUEST)
            return None

    def require_user(self):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        session_cookie = cookie.get(SESSION_COOKIE)
        user = parse_session(session_cookie.value if session_cookie else None)
        if not user:
            self.respond_json({"error": "Sesion no iniciada."}, HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def serve_static(self, path: str):
        file_info = STATIC_FILES.get(path)
        if not file_info:
            self.send_error(HTTPStatus.NOT_FOUND, "Archivo no encontrado.")
            return
        filename, content_type = file_info
        file_path = BASE_DIR / filename
        if not file_path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Archivo no encontrado.")
            return
        content = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def respond_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK):
        content = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        return


def main():
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), AmbulanceHandler)
    print(f"Servidor activo en http://{HOST}:{PORT} usando {db.engine}")
    server.serve_forever()


if __name__ == "__main__":
    main()
