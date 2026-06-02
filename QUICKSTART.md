# Quick Start — Aqualia para Home Assistant

## Instalación en 3 pasos

### 1. Instalar via HACS

1. Abre **HACS → Integraciones**.
2. Menú **⋮** → **Repositorios personalizados**.
3. URL: `https://github.com/eclyptox/aqualia-ha` · Categoría: **Integración** → **Añadir**.
4. Busca **Aqualia** en HACS → **Descargar** → **Reiniciar Home Assistant**.

### 2. Añadir la integración

1. Ve a **Ajustes → Dispositivos y servicios → Añadir integración**.
2. Busca **Aqualia**.
3. **Paso 1 — Credenciales**: introduce tu NIF y contraseña de Aqualia.
4. **Paso 2 — Contrato**: si la detección automática funciona, selecciona tu contrato del desplegable. Si no, introduce los códigos manualmente (ver README).
5. Acepta. La integración valida las credenciales y crea los sensores.

### 3. Añadir al Energy Dashboard (opcional)

1. Ve a **Ajustes → Dashboards → Energía → Agua**.
2. Añade `sensor.aqualia_total_consumption`.

---

## Troubleshooting

| Problema | Solución |
|----------|----------|
| Error de credenciales | Verifica NIF (sin espacios) y contraseña en `oficinavirtual.aqualia.es` |
| Discovery no encuentra contratos | Introduce los códigos manualmente (ver README) |
| Sensores `unavailable` | Revisa los logs en **Ajustes → Sistema → Logs** filtrando por `aqualia` |
| Energy Dashboard no muestra agua | Asegúrate de haber añadido `sensor.aqualia_total_consumption`, no otro sensor |
