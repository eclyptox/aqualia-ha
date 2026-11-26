# Documentación

| Documento | Para quién | Contenido |
| --- | --- | --- |
| [QUICKSTART.md](QUICKSTART.md) | Usuarios | Instalación por HACS en 5 minutos |
| [README.md](README.md) | Usuarios | Instalación, configuración, sensores, Energy Dashboard, notificaciones de factura y solución de problemas |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Desarrolladores | Entorno, tests, arquitectura, cómo añadir sensores y probar en un HA real |
| [DOCS.md](DOCS.md) | Desarrolladores | Referencia de la API de Aqualia: cabeceras, login cifrado, contratos, consumo y facturas |
| [RELEASING.md](RELEASING.md) | Mantenedores | CI local (hook pre-push) y publicación de versiones para HACS |
| [CLAUDE.md](CLAUDE.md) | Agentes de IA | Invariantes y convenciones del código para Claude Code |

## El repositorio

- `custom_components/aqualia/` — la integración (lo que instala HACS).
- `tests/` — tests con pytest; no necesitan Home Assistant instalado.
- `scripts/ci.sh` y `.githooks/pre-push` — CI local (no hay CI en GitHub).
- `aqualia/` — add-on MQTT legacy. No se mantiene y no funciona desde noviembre de 2026 (usa el login
  sin cifrar que Aqualia dejó de aceptar). Se conserva solo como referencia histórica.
