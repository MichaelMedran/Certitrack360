"""Configuración de CertiTrack 360. Todo se lee de variables de entorno (ver .env.example y SDD §18.2)."""
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env():
    """Lee un archivo .env simple (sin dependencias externas)."""
    ruta = BASE_DIR / ".env"
    if ruta.exists():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_cargar_env()


def _bool(nombre, defecto):
    return os.environ.get(nombre, defecto).strip().lower() in ("1", "true", "yes", "si", "sí")


def _lista(nombre, defecto):
    return [x.strip() for x in os.environ.get(nombre, defecto).split(",") if x.strip()]


def _base_de_datos(url):
    """Convierte DATABASE_URL en la configuración de Django.

    sqlite:///db.sqlite3 (relativa al proyecto) · sqlite:////ruta/absoluta.sqlite3
    postgres://usuario:clave@host:5432/nombre
    """
    u = urlparse(url)
    if u.scheme in ("postgres", "postgresql"):
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": u.path.lstrip("/"),
            "USER": unquote(u.username or ""),
            "PASSWORD": unquote(u.password or ""),
            "HOST": u.hostname or "",
            "PORT": str(u.port or ""),
        }
    if u.scheme == "sqlite":
        ruta = Path(unquote(u.path)[1:])
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": ruta if ruta.is_absolute() else BASE_DIR / ruta}
    raise ImproperlyConfigured("DATABASE_URL debe comenzar con sqlite:// o postgres://")


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "clave-solo-para-desarrollo-local")
DEBUG = _bool("DJANGO_DEBUG", "1")
ALLOWED_HOSTS = _lista("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.cuentas",
    "apps.clientes",
    "apps.entregables",
    "apps.calendario",
    "apps.alertas",
    "apps.consolidado",
    "apps.conocimiento",
    "apps.reportes",
    "apps.levantamiento",
    "apps.indicadores",
    "apps.repositorio",
    "apps.busqueda",
    "apps.equipo",
    # Sprint 3 (SDD del Sprint 3, §5)
    "apps.etiquetas",
    "apps.urgencias",
    "apps.checklists",
    "apps.facturacion",
    "apps.exportacion",
    "apps.extraccion",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # estáticos en producción (RF-51): servir no necesita otro servidor web
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.cuentas.middleware.SinCacheEnPaginasPrivadas",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.cuentas.middleware.CabecerasDeSeguridad",  # política de contenido sin orígenes externos (RF-51, RNF-16)
]

ROOT_URLCONF = "certitrack.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.alertas.context_processors.notificaciones",
                "apps.cuentas.context_processors.navegacion",
                "apps.urgencias.context_processors.urgentes",
                "apps.cuentas.context_processors.plataforma",
            ],
        },
    },
]

WSGI_APPLICATION = "certitrack.wsgi.application"

DATABASES = {"default": _base_de_datos(os.environ.get("DATABASE_URL", "sqlite:///db.sqlite3"))}

AUTH_USER_MODEL = "cuentas.Usuario"
# Bloqueo temporal de intentos de ingreso fallidos (RF-51): vale también para el panel /admin/.
AUTHENTICATION_BACKENDS = ["apps.cuentas.backends.ModelBackendConBloqueo"]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Solo al correr las pruebas: un hash rápido para no perder minutos calculando PBKDF2 en cada usuario de prueba.
# En la aplicación real se usa el predeterminado de Django (PBKDF2); hay una prueba que lo verifica.
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "login"

# Sesión: se cierra por inactividad (cada petición renueva el plazo). Valor propuesto, configurable.
SESSION_IDLE_MINUTES = int(os.environ.get("SESSION_IDLE_MINUTES", "60"))
SESSION_COOKIE_AGE = SESSION_IDLE_MINUTES * 60
SESSION_SAVE_EVERY_REQUEST = True
# Cookies «seguras» solo viajan por HTTPS: activas por defecto fuera de DEBUG.
# En una red interna sin HTTPS, fijar DJANGO_COOKIE_SECURE=0.
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = _bool("DJANGO_COOKIE_SECURE", "0" if DEBUG else "1")
# Detrás de un proxy o túnel que termina HTTPS (p. ej. la demostración remota con Cloudflare):
# confiar en X-Forwarded-Proto para que Django sepa que la petición original fue HTTPS (CSRF y cookies seguras).
# Activarlo solo si de verdad hay un proxy delante; si no, cualquiera podría falsear la cabecera.
if _bool("DJANGO_BEHIND_PROXY", "0"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = _lista("DJANGO_CSRF_TRUSTED_ORIGINS", "")

LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# WhiteNoise sirve también lo que aún no se recopiló con collectstatic (manage.py servir lo recopila al arrancar).
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = DEBUG
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Alertas: días antes del vencimiento en que se genera una notificación (una sola por umbral y destinatario).
# Es la única fuente de verdad de la urgencia: próximo = el mayor umbral; crítico = el segundo mayor de los positivos
# (con un solo umbral positivo, ese). Por defecto 5,2,1,0 (SDD del Sprint 2, §10.1 y RF-22): suma el aviso de 24 h y
# «crítico» sigue empezando a 2 días.
ALERT_THRESHOLDS_DAYS = [int(x) for x in _lista("ALERT_THRESHOLDS_DAYS", "5,2,1,0")]

# Código del entregable (SDD del Sprint 2, RF-20): <prefijo>-<año de creación>-<id con 5 dígitos>, p. ej. CT-2026-00031.
CODIGO_PREFIJO = os.environ.get("CODIGO_PREFIJO", "CT").strip()
if not re.fullmatch(r"[A-Za-z0-9]{1,10}", CODIGO_PREFIJO):
    raise ImproperlyConfigured("CODIGO_PREFIJO debe tener de 1 a 10 letras o números, sin espacios ni guiones.")

# Entregas (SDD del Sprint 2, RF-29 y §7.4): días que el acta de conformidad puede seguir pendiente antes de avisar (una sola
# vez por entrega) al junior asignado y al senior revisor.
ACTA_DIAS_PENDIENTE = int(os.environ.get("ACTA_DIAS_PENDIENTE", "5"))
if ACTA_DIAS_PENDIENTE < 0:
    raise ImproperlyConfigured("ACTA_DIAS_PENDIENTE no puede ser negativo.")

# Ficha de levantamiento (SDD del Sprint 2, RF-30 y §7.5): máximo de entregables por confirmación de ficha.
FICHA_MAX_ENTREGABLES = int(os.environ.get("FICHA_MAX_ENTREGABLES", "60"))
if FICHA_MAX_ENTREGABLES <= 0:
    raise ImproperlyConfigured("FICHA_MAX_ENTREGABLES debe ser mayor que cero.")

# Personal y asignación (SDD del Sprint 2, RF-31 y §7.6): umbral de sobrecarga de entregables activos.
try:
    CARGA_MAXIMA_ACTIVOS = int(os.environ.get("CARGA_MAXIMA_ACTIVOS", "8"))
except ValueError as exc:
    raise ImproperlyConfigured("CARGA_MAXIMA_ACTIVOS debe ser un número entero mayor que cero.") from exc
if CARGA_MAXIMA_ACTIVOS <= 0:
    raise ImproperlyConfigured("CARGA_MAXIMA_ACTIVOS debe ser mayor que cero.")

# Buscador global (SDD del Sprint 2, RF-36 y §10.1): límite de resultados por grupo.
try:
    BUSCADOR_LIMITE = int(os.environ.get("BUSCADOR_LIMITE", "20"))
except ValueError as exc:
    raise ImproperlyConfigured("BUSCADOR_LIMITE debe ser un número entero mayor que cero.") from exc
if BUSCADOR_LIMITE <= 0:
    raise ImproperlyConfigured("BUSCADOR_LIMITE debe ser mayor que cero.")

# ------------------------------------------------------------------ Sprint 3 (SDD del Sprint 3, §10.1)

def _entero(nombre, defecto, minimo=1):
    try:
        valor = int(os.environ.get(nombre, defecto))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{nombre} debe ser un número entero.") from exc
    if valor < minimo:
        raise ImproperlyConfigured(f"{nombre} debe ser {minimo} o más.")
    return valor


def _horario(texto):
    """«1-5,09:00-18:00» → (días laborales como conjunto de 1 (lunes) a 7, hora de inicio, hora de fin)."""
    import datetime

    try:
        dias, horas = texto.split(",")
        d1, d2 = (int(x) for x in dias.split("-"))
        inicio, fin = (datetime.time.fromisoformat(x.strip()) for x in horas.split("-"))
        if not (1 <= d1 <= d2 <= 7) or inicio >= fin:
            raise ValueError
    except ValueError as exc:
        raise ImproperlyConfigured("HORARIO_LABORAL debe tener la forma 1-5,09:00-18:00 (días 1 = lunes a 7).") from exc
    return set(range(d1, d2 + 1)), inicio, fin


# Prioridad (RF-42): días para que un entregable normal de cliente Estratégico sea de prioridad Media.
PRIORIDAD_DIAS_ESTRATEGICO = _entero("PRIORIDAD_DIAS_ESTRATEGICO", "10")

# Alerta de urgencia (RF-43): horario laboral (para marcar «fuera de horario») y correo opcional por un servidor LOCAL.
HORARIO_LABORAL = _horario(os.environ.get("HORARIO_LABORAL", "1-5,09:00-18:00"))
EMAIL_HOST = os.environ.get("EMAIL_HOST", "").strip()
EMAIL_PORT = _entero("EMAIL_PORT", "25")
DEFAULT_FROM_EMAIL = os.environ.get("EMAIL_FROM", "certitrack@localhost")
# Sin servidor de correo configurado no se envía nada (los avisos quedan dentro de la plataforma).
EMAIL_BACKEND = ("django.core.mail.backends.smtp.EmailBackend" if EMAIL_HOST
                 else "django.core.mail.backends.dummy.EmailBackend")

# Facturación (RF-46): conector de solo lectura. El simulado lee la tabla FacturaSimulada del servidor local.
FACTURACION_CONECTOR = os.environ.get("FACTURACION_CONECTOR", "apps.facturacion.conector.ConectorSimulado")

# Extracción de datos (RF-48): Tesseract es un programa del servidor; sin él solo se lee el texto de los PDF que lo traen.
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "tesseract").strip()
OCR_IDIOMAS = os.environ.get("OCR_IDIOMAS", "spa+eng").strip()
OCR_CONFIANZA_MINIMA = _entero("OCR_CONFIANZA_MINIMA", "60", minimo=0)
OCR_MAX_PAGINAS = _entero("OCR_MAX_PAGINAS", "10")

# Plataforma independiente (RF-51): único origen externo permitido (vacío: ninguno) y bloqueo de intentos de ingreso.
FILEDOC_URL = os.environ.get("FILEDOC_URL", "").strip()
_filedoc = urlparse(FILEDOC_URL)
if FILEDOC_URL and (_filedoc.scheme not in ("http", "https") or not _filedoc.netloc):
    raise ImproperlyConfigured("FILEDOC_URL debe ser una dirección completa, p. ej. https://filedoc.certicom.local")
# Solo el origen (esquema y servidor) entra en la cabecera Content-Security-Policy; vacío si no hay Filedoc.
FILEDOC_ORIGEN = f"{_filedoc.scheme}://{_filedoc.netloc}" if FILEDOC_URL else ""
LOGIN_MAX_INTENTOS = _entero("LOGIN_MAX_INTENTOS", "5")
LOGIN_BLOQUEO_MINUTOS = _entero("LOGIN_BLOQUEO_MINUTOS", "15")
SERVIDOR_PUERTO = _entero("SERVIDOR_PUERTO", "8000")
SERVIDOR_HILOS = _entero("SERVIDOR_HILOS", "8")

# Adjuntos de los entregables: se guardan en disco local y NO se sirven por una URL pública.
# MEDIA_URL = None impide que Django construya direcciones a los archivos; no hay ruta de medios en urls.py
# y toda descarga pasa por una vista que verifica los permisos del entregable.
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))
MEDIA_URL = None
MEDIA_MAX_UPLOAD_MB = float(os.environ.get("MEDIA_MAX_UPLOAD_MB", "10"))
ALLOWED_UPLOAD_EXTENSIONS = [e.lower().lstrip(".") for e in _lista("ALLOWED_UPLOAD_EXTENSIONS", "pdf,docx,xlsx,pptx,png,jpg,txt")]

# Consolidado del gerente: ventana (en días) de «próximos a vencer».
CONSOLIDADO_WINDOW_DAYS = int(os.environ.get("CONSOLIDADO_WINDOW_DAYS", "7"))

# Asistente (fase 2): todo en el servidor local.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
# Similitud mínima (0 a 1) para considerar relevante una lección; ajustar según el modelo de embeddings.
ASSISTANT_MIN_SIMILARITY = float(os.environ.get("ASSISTANT_MIN_SIMILARITY", "0.5"))
