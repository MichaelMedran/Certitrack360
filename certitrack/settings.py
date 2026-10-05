"""Configuración de CertiTrack 360. Todo se lee de variables de entorno (ver .env.example y SDD §18.2)."""
import os
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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
            ],
        },
    },
]

WSGI_APPLICATION = "certitrack.wsgi.application"

DATABASES = {"default": _base_de_datos(os.environ.get("DATABASE_URL", "sqlite:///db.sqlite3"))}

AUTH_USER_MODEL = "cuentas.Usuario"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

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

LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Alertas: días antes del vencimiento en que se genera una notificación.
# Es la única fuente de verdad de la urgencia: crítico = el menor umbral positivo, próximo = el mayor.
ALERT_THRESHOLDS_DAYS = [int(x) for x in _lista("ALERT_THRESHOLDS_DAYS", "5,2,0")]

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
