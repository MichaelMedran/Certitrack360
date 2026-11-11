# Guía de despliegue en un servidor propio de CERTICOM

Esta guía cubre lo que depende del software (SDD del Sprint 3, §7.12, RF-51, HU-09). La instalación física del servidor, la red interna y
el nombre de dominio interno son tarea del área de Sistemas (decisión D9 del SDD).

## 1. Qué se instala

| Pieza | Para qué | Notas |
|---|---|---|
| Python 3.12 | Ejecuta la aplicación | En Windows o Linux |
| PostgreSQL 16 | Base de datos de producción | SQLite solo sirve para desarrollo |
| Esta aplicación | `manage.py servir` (waitress + WhiteNoise) | No hace falta nginx ni Apache; pueden ir delante si Sistemas ya los usa |
| Tesseract (opcional) | Lectura de documentos escaneados (RF-48) | Programa del servidor; sin él solo se lee el texto de los PDF que lo traen |
| Ollama (opcional) | Asistente de lecciones (fase 2) | Local; sin puertos publicados |

Ningún componente se conecta a internet para funcionar (RNF-15 y RNF-16).

## 2. Instalación

```powershell
git clone <repositorio> certitrack360 ; cd certitrack360
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt      # Linux: .venv/bin/pip
copy .env.example .env                               # Linux: cp .env.example .env
```

Edite `.env` (nunca lo suba al repositorio):

| Variable | Valor en producción |
|---|---|
| `DJANGO_SECRET_KEY` | Una clave larga y aleatoria propia |
| `DJANGO_DEBUG` | `0` |
| `DJANGO_ALLOWED_HOSTS` | El nombre interno que asigne Sistemas, p. ej. `certitrack.certicom.local` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | La misma dirección con esquema, p. ej. `https://certitrack.certicom.local` |
| `DJANGO_COOKIE_SECURE` | `1` si se sirve por HTTPS; `0` si es HTTP en la red interna (con `0` activo, las cookies viajan sin cifrar) |
| `DATABASE_URL` | `postgres://usuario:clave@servidor:5432/certitrack` |
| `FILEDOC_URL` | La dirección de Filedoc (única salida permitida) o vacío si no hay |
| `LOGIN_MAX_INTENTOS`, `LOGIN_BLOQUEO_MINUTOS` | `5` y `15` (por defecto) |
| `SERVIDOR_PUERTO`, `SERVIDOR_HILOS` | `8000` y `8` (por defecto) |

Con `DJANGO_DEBUG=0` las cookies seguras están activas por defecto: si el sitio se atiende por HTTP, fije `DJANGO_COOKIE_SECURE=0` o nadie podrá ingresar.
Si hay un proxy que termina HTTPS delante, active además `DJANGO_BEHIND_PROXY=1` (solo en ese caso).

Primera puesta en marcha:

```powershell
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py createsuperuser     # crea al administrador técnico (rol ADMIN)
.\.venv\Scripts\python manage.py servir
```

`servir` recopila los estáticos (`collectstatic`) y escucha en `0.0.0.0:SERVIDOR_PUERTO`. Opciones: `--host`, `--puerto`, `--hilos`, `--sin-estaticos`.
Se detiene con Ctrl+C. **No cargue `seed_demo` en producción**: son datos simulados.

## 3. Que arranque solo

- **Windows:** cree una tarea programada («Al iniciar el sistema», con una cuenta de servicio sin privilegios) que ejecute
  `C:\certitrack360\.venv\Scripts\python.exe manage.py servir` con carpeta de inicio `C:\certitrack360`; otra igual con `manage.py programador`.
  También sirve NSSM u otro administrador de servicios.
- **Linux:** dos unidades de systemd (`certitrack-web.service` con `ExecStart=.../python manage.py servir` y `certitrack-programador.service` con
  `manage.py programador`), con `Restart=always` y `WorkingDirectory` en la carpeta de la aplicación.
- **Docker Compose:** `docker compose up --build -d`. La imagen ya usa `manage.py servir`; los servicios `web` y `programador` se reinician con el motor de contenedores.

## 4. El programador

`manage.py programador` debe estar siempre corriendo, junto a `servir`. Hace las alertas de vencimiento y de actas pendientes (cada hora), la indexación de
lecciones (a diario a las 02:00, hora de Lima) y los reportes periódicos de avance. Si se detiene, la plataforma funciona pero deja de avisar.

## 5. Copias de respaldo

Respalde juntos, para que sean coherentes entre sí:

1. **La base de datos:** `pg_dump -Fc -U certitrack certitrack > respaldo-AAAAMMDD.dump` (restauración: `pg_restore`).
2. **Los adjuntos:** la carpeta `media/` (o la de `MEDIA_ROOT`). No tienen URL pública; sin ellos, la base apunta a archivos que no existen.
3. **El archivo `.env`**, guardado aparte y con acceso restringido (contiene claves).

Frecuencia mínima: diaria, con una copia fuera del servidor. Pruebe la restauración en otra máquina al menos una vez.

## 6. Actualizar la versión

```powershell
git pull
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python manage.py migrate
```

Reinicie `servir` y `programador`. Respalde antes de migrar.

## 7. Seguridad que ya trae la aplicación

- **Sin salida de datos (RNF-16):** cada respuesta lleva `Content-Security-Policy: default-src 'self'`; los formularios y las peticiones del navegador solo
  pueden ir al propio servidor y a `FILEDOC_URL`. No se permiten scripts en línea ni bibliotecas de terceros: todo está en `static/`. `Referrer-Policy: same-origin`.
- **Bloqueo de intentos de ingreso:** tras `LOGIN_MAX_INTENTOS` fallos de un usuario desde una misma dirección, ese usuario queda bloqueado
  `LOGIN_BLOQUEO_MINUTOS` desde esa dirección (también en `/admin/`). Un ingreso acertado reinicia la cuenta. Los intentos quedan en la tabla `IntentoIngreso`
  (visible en el panel técnico) y se conservan 30 días.
- Contraseñas validadas, cierre de sesión por inactividad (`SESSION_IDLE_MINUTES`), cookies seguras y páginas privadas sin caché.
- La dirección del cliente se toma de la conexión directa. Detrás de un proxy inverso todos los intentos parecerán venir del proxy: el bloqueo seguirá
  funcionando por usuario, pero compartiendo la dirección entre todos.

## 8. Comprobación después de instalar

1. `http://<nombre-interno>:<puerto>/login/` carga con estilos (los estáticos los sirve la propia aplicación).
2. Ingrese con el administrador y revise `/admin/`.
3. Con la consola del navegador abierta, ninguna pantalla debe mostrar errores de «Content Security Policy» ni pedir recursos de otros sitios.
4. Equivoque la contraseña de un usuario de prueba cinco veces: el sexto intento debe mostrar el aviso de bloqueo.
5. Confirme que `programador` está corriendo y que el respaldo de la noche se generó.
