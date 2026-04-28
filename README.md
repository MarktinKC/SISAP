# Agenda de Viajes de Ambulancia

Proyecto listo para desplegar en Render con:

- backend Python nativo
- autenticacion por cookie firmada
- base de datos PostgreSQL en produccion
- SQLite como respaldo local para desarrollo

## Ejecutar localmente

Desde esta carpeta:

```powershell
powershell -ExecutionPolicy Bypass -File .\serve.ps1
```

Abrir:

`http://127.0.0.1:8000`

Usuario local inicial:

- usuario: `admin`
- contrasena: `admin123`

## Deploy en Render

Este repo incluye [render.yaml](C:/Users/rock_/Documents/Codex/2026-04-27/crear-sitio-web-con-login-de/render.yaml), asi que puedes usar un Blueprint.

### Pasos

1. Sube este proyecto a GitHub.
2. En Render, elige `New +` -> `Blueprint`.
3. Conecta el repositorio.
4. Render creara:
   - un Web Service
   - una base PostgreSQL
5. Antes de finalizar, define la variable `ADMIN_PASSWORD` con una contrasena segura.
6. Espera a que termine el build y abre la URL publica.

## Variables importantes

- `APP_ENV=production`
- `DATABASE_URL`
- `SECRET_KEY`
- `COOKIE_SECURE=true`
- `ADMIN_USERNAME`
- `ADMIN_FULL_NAME`
- `ADMIN_PASSWORD`
- `PORT` lo asigna Render automaticamente

## Notas

- En produccion, si no defines `ADMIN_PASSWORD`, no se crea usuario administrador inicial.
- El sistema permite registrar usuarios nuevos desde la pantalla de acceso.
- Para Render se recomienda usar PostgreSQL y no subir `ambulance.db`.
