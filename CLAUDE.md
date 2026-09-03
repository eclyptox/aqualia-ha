# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Qué es este repo

Integración personalizada de Home Assistant (`custom_components/aqualia`) que consulta la API de la
oficina virtual de Aqualia y expone sensores de consumo de agua y facturación. Se distribuye vía HACS.

La carpeta `aqualia/` en la raíz es el **add-on MQTT legacy** (Docker + `paho-mqtt`), predecesor de la
integración. No se mantiene y no forma parte de la ruta de instalación recomendada. Los cambios
funcionales van en `custom_components/aqualia/`.

## Comandos

```bash
# Dependencias de test (Home Assistant NO se instala; voluptuous SÍ hace falta)
pip install -r requirements-test.txt

# Todos los tests
python3 -m pytest

# Un fichero / una clase / un test
python3 -m pytest tests/test_coordinator.py
python3 -m pytest tests/test_coordinator.py::TestShouldFetchInvoices
python3 -m pytest tests/test_sensor.py -k stale

# Cobertura
python3 -m pytest --cov=custom_components/aqualia
```

No hay linter configurado. `.github/workflows/ci.yml` ejecuta pytest + hassfest + validación HACS.

## Arquitectura

Flujo de datos: `AqualiaClient` (HTTP síncrono) → `ConsumptionParser` / `InvoiceParser` →
`AqualiaDataUpdateCoordinator` → entidades `SensorEntity`.

- **`api.py`** — todo lo que toca la red y el parseo, sin dependencias de Home Assistant. Contiene
  `AqualiaClient` (login JWT, consumo, contratos, facturas), `ConsumptionParser` e `InvoiceParser`.
  Es el único módulo testeable de forma totalmente aislada.
- **`coordinator.py`** — `DataUpdateCoordinator` que ejecuta el cliente síncrono en el executor
  (`hass.async_add_executor_job` + `partial`).
- **`sensor.py`** — descripciones declarativas de sensores + dos clases de entidad.
- **`config_flow.py`** — flujo de dos pasos (credenciales → contrato), más `async_step_reauth`
  y `AqualiaOptionsFlow`.

### Dos cadencias de refresco distintas

El coordinator hace **una** llamada de consumo por ciclo (`poll_interval_minutes`, por defecto 60),
pero las facturas solo se piden cada `INVOICE_FETCH_INTERVAL` (12 h) y se sirven desde
`_cached_invoice_data` el resto del tiempo. Un fallo al traer facturas se registra como warning y
mantiene la caché — nunca tumba la actualización de consumo.

### Contrato: dos identificadores diferentes

La API usa **dos formas** del contrato y esto es fuente habitual de bugs:

- `Contract` (4 campos: `CacCode`, `ContractCode`, `InstallationCode`, `ContractNumber`) → endpoint
  de consumo.
- `ContractIdentifier` (los 4 anteriores **más** `MunicipalityCode`, `EntryDate`,
  `ContractStatusCode`, `ContractStatus`, `styleClass`) → endpoint de facturas.

Las entradas de configuración creadas antes de que se capturaran los campos extra solo tienen los 4
primeros. `coordinator._resolve_contract_identifier()` los resuelve al vuelo desde
`GetUserLinkedContracts` para no obligar a reconfigurar. Al tocar el flujo de facturas hay que
preservar esa ruta de compatibilidad.

### Estrategia de disponibilidad de los sensores

Tres comportamientos distintos, controlados por flags en `AqualiaSensorDescription`:

- `stale_unavailable=True` — pasa a `unavailable` si la última lectura tiene más de `_STALE_DAYS` (7).
  Es deliberado: permite automatizaciones con trigger `state → unavailable`.
- `requires_data=True` — sensores de factura; `unavailable` mientras su clave sea `None`.
- El acumulado (`AqualiaCumulativeSensor`) y los sensores base **nunca** se caen por un fallo puntual
  de la API: conservan el último valor y añaden el atributo `api_error`.

### Invariante del `total_increasing`

`ConsumptionParser._reading_index()` y `AqualiaCumulativeSensor.native_value` devuelven `None`, no
`0`, cuando la API manda un `ReadingIndex` vacío o cero. Emitir `0` haría que HA contase el valor
completo del odómetro como consumo nuevo al volver la lectura real. No "simplificar" esos `if value`.

### Normalización del retraso de lecturas

Aqualia entrega lecturas con 2-3 días de retraso y a veces agrupadas (una lectura que cubre 3 días).
`reading_gap_days` mide ese hueco y `daily_normalized` divide por él. `avg_daily_30d` aplica la misma
corrección por lectura. Cualquier métrica diaria nueva debe normalizar igual.

### Opciones: `entry.options` gana, `entry.data` es el respaldo

`poll_interval_minutes` y `days_back` se leen siempre con `coordinator.get_option()`, que consulta
`entry.options` primero y cae a `entry.data`. Las entradas creadas antes del options flow guardan
esos valores en `data`; nunca leas `entry.data` directamente para estos dos campos. Al guardar
opciones, el listener registrado en `__init__.py` recarga la entrada para aplicar el intervalo nuevo.

### Datos malformados: descartar, nunca propagar

La API devuelve `null` en importes y fechas de forma intermitente, y algún `IssueDate` no ISO. Un
`TypeError` aquí congelaba todos los sensores (consumo) o dejaba las facturas fijadas a la caché para
siempre. Todo valor numérico pasa por `_to_float()` y toda fecha por `_parse_datetime()`, que
devuelve `None` en vez de lanzar; `ConsumptionParser` descarta las lecturas sin fecha válida con un
warning. Al añadir un campo nuevo, léelo con esos helpers.

### Zona horaria en las métricas de calendario

`today_consumption` y `monthly_total` dependen del límite de día **local**, no del de UTC. El
coordinator resuelve la zona con `resolve_timezone(hass)` y la pasa a `fetch_metrics(tz=...)` →
`ConsumptionParser(readings, tz=...)`. `api.py` sigue sin importar nada de Home Assistant: recibe un
`tzinfo` y por defecto usa UTC. Cualquier métrica ligada a un calendario debe usar `self.tz`.

### Nombres de entidad: traducción, no `_attr_name`

Los sensores declaran `translation_key` y **no** asignan `_attr_name` — hacerlo anularía la
traducción. HA resuelve por este orden: `_attr_name` → traducción → `entity_description.name`, así
que el campo `name` en inglés de cada descripción queda como respaldo si falta una clave. Al añadir
un sensor hay que añadir su clave a `strings.json`, `translations/en.json` y `translations/es.json`;
los tres se mantienen sincronizados y `strings.json`/`en.json` van en inglés.

## Convenciones de testing

Home Assistant **no** es una dependencia de test. `tests/conftest.py` llama a
`tests.ha_stubs._install()` en el import de nivel de módulo, antes de cualquier import del componente,
inyectando módulos falsos en `sys.modules`. Consecuencia práctica: **si añades un import nuevo de
`homeassistant.*` en el componente, hay que añadir el stub correspondiente en `tests/ha_stubs.py`** o
los tests fallarán al importar.

`pytest.ini` define `pythonpath = custom_components .`, por lo que los tests importan como
`from aqualia.sensor import ...` — ese `aqualia` es `custom_components/aqualia`, **no** la carpeta
`aqualia/` legacy de la raíz (gana el primer elemento del pythonpath).

`voluptuous` sí es una dependencia real de test: sin él `config_flow.py` no se puede importar
siquiera. No lo stubees — los esquemas del flujo son precisamente lo que hay que validar.

Los tests async necesitan `@pytest.mark.asyncio` explícito (pytest-asyncio en modo STRICT).

Los tests del coordinator invocan métodos sin instanciar la clase
(`AqualiaDataUpdateCoordinator._should_fetch_invoices(mock)`) para evitar el `__init__` de HA. Sigue
ese patrón para lógica nueva del coordinator.

## Detalles de la API de Aqualia

Base: `https://oficinavirtualapi.aqualia.es/ofcvirtual`. Requiere cabeceras `Application-Id: 1`,
`Country: 34` y `Origin`/`Referer` de `oficinavirtual.aqualia.es`; sin ellas rechaza las peticiones.

El token JWT se asume válido 8 h con margen de renovación de 5 min. Ante un `401` el cliente limpia
el token, vuelve a loguear y reintenta **una** vez (patrón `_request_*` devuelve `None` en 401 →
el método público reintenta). El login tiene backoff de 5/15/60 s en errores de red, pero
`AqualiaAuthError` (401/403) se propaga inmediatamente sin reintentos.

Campos de las lecturas: `DateTimeConsumptionCurve`, `ConsumptionValue` (litros del intervalo),
`ReadingIndex` (odómetro acumulado).

## Convenciones

- Nombres de entidad y comentarios de código en inglés; documentación de usuario, mensajes del
  config flow y notificaciones en español.
- `manifest.json` → `version` debe subirse en cada release para que HACS ofrezca la actualización.
- Los sensores de importe usan `"EUR"` (ISO 4217), no `"€"`: es lo que exige `device_class: monetary`.
  Cambiar la unidad de un sensor ya desplegado obliga al usuario a migrar sus estadísticas.
