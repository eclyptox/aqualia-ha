# Desarrollo

Guía para modificar la integración `custom_components/aqualia`. La referencia de la API de Aqualia está
en [DOCS.md](DOCS.md) y el proceso de publicación en [RELEASING.md](RELEASING.md).

## Entorno

Requisitos: Python 3.12+, Docker (para hassfest y la validación HACS) y `gh` autenticado (validación HACS).

```bash
git clone https://github.com/eclyptox/aqualia-ha.git
cd aqualia-ha
pip install -r requirements-test.txt
git config core.hooksPath .githooks   # activa la CI local en cada push
```

Home Assistant **no** se instala: los tests usan stubs (ver más abajo).

## Tests

```bash
python3 -m pytest                                          # todo
python3 -m pytest tests/test_api_client.py                 # un fichero
python3 -m pytest tests/test_coordinator.py::TestShouldFetchInvoices
python3 -m pytest tests/test_sensor.py -k stale            # por nombre
python3 -m pytest --cov=custom_components/aqualia          # cobertura
scripts/ci.sh                                              # CI completa (pytest + hassfest + HACS)
```

Convenciones:

- `tests/conftest.py` instala `tests/ha_stubs.py` en `sys.modules` antes de importar el componente.
  **Si añades un import nuevo de `homeassistant.*`, añade su stub** o los tests fallarán al importar.
- `pytest.ini` define `pythonpath = custom_components .`: los tests importan `from aqualia.api import …`,
  y ese `aqualia` es `custom_components/aqualia`, no la carpeta legacy de la raíz.
- `voluptuous` es una dependencia real: los esquemas del config flow son justo lo que hay que validar.
- Los tests async necesitan `@pytest.mark.asyncio` (pytest-asyncio en modo estricto).
- La lógica del coordinator se prueba llamando a los métodos sin instanciar la clase
  (`AqualiaDataUpdateCoordinator._should_fetch_invoices(mock)`) para evitar el `__init__` de HA.
- Los tests del login generan una clave RSA propia y simulan la respuesta cifrada de Aqualia
  (`_encrypted_login_response` en `tests/test_api_client.py`); la pausa tras un 429 se reinicia en
  cada test con un fixture `autouse`.

## Estructura

```
custom_components/aqualia/
├── __init__.py        # setup/unload de la entrada y recarga al cambiar opciones
├── api.py             # AqualiaClient + ConsumptionParser + InvoiceParser (sin imports de HA)
├── coordinator.py     # DataUpdateCoordinator: consumo cada ciclo, facturas cada 12 h
├── sensor.py          # descripciones declarativas y las dos clases de entidad
├── config_flow.py     # credenciales → contrato, reauth y options flow
├── const.py           # claves de configuración, valores por defecto y límites
├── manifest.json      # versión (súbela en cada release)
├── strings.json       # textos base (inglés)
├── translations/      # en.json y es.json
└── brand/             # iconos y logos
scripts/ci.sh          # CI local
.githooks/pre-push     # lanza scripts/ci.sh antes de cada push
tests/                 # pytest + stubs de HA
aqualia/               # add-on MQTT legacy (no mantenido, no funciona desde 11/2026)
```

## Arquitectura

```
AqualiaClient (HTTP síncrono, en executor)
   → ConsumptionParser / InvoiceParser
   → AqualiaDataUpdateCoordinator
   → AqualiaSensor / AqualiaCumulativeSensor
```

Puntos que conviene conocer antes de tocar nada:

- **Dos cadencias.** El consumo se pide en cada ciclo (`poll_interval_minutes`, 60 por defecto); las
  facturas solo cada 12 h y se sirven desde caché el resto del tiempo. Un fallo de facturas es un
  warning y nunca tumba el consumo.
- **Dos formas del contrato.** `Contract` (4 campos) para consumo y `ContractIdentifier` (9 campos) para
  facturas. Las entradas antiguas solo guardan los 4 primeros y
  `coordinator._resolve_contract_identifier()` completa el resto al vuelo. No rompas esa ruta.
- **Login cifrado y pausa tras 429.** Ver [DOCS.md](DOCS.md#login-cifrado). La pausa vive a nivel de
  módulo (`_LOGIN_COOLDOWN_UNTIL`, por NIF) porque HA crea un cliente nuevo en cada reintento de arranque.
- **`total_increasing`.** `ReadingIndex` vacío o `0` se convierte en `None`, nunca en `0`: un 0
  transitorio haría que HA contase el odómetro entero como consumo nuevo.
- **Retraso de lecturas.** Cualquier métrica diaria debe dividir por `reading_gap_days`, igual que
  `daily_normalized` y `avg_daily_30d`.
- **Zona horaria.** "Hoy" y "este mes" usan la zona de HA (`resolve_timezone(hass)` → `tz=`); `api.py`
  recibe un `tzinfo` y no importa nada de HA.
- **Datos malformados.** Todo número pasa por `_to_float()` y toda fecha por `_parse_datetime()`, que
  devuelven `None` en vez de lanzar.
- **Opciones.** `poll_interval_minutes` y `days_back` se leen con `get_option()` (`entry.options` y, si no,
  `entry.data`). Nunca directamente de `entry.data`.
- **Disponibilidad.** `stale_unavailable` (sin lecturas en más de 7 días), `requires_data` (facturas) y el
  acumulado, que nunca cae por un fallo puntual: conserva el valor y añade `api_error`.

## Añadir un sensor

1. Añade la métrica en el parser correspondiente de `api.py`, leyendo los campos con `_to_float()` /
   `_parse_datetime()`.
2. Declara un `AqualiaSensorDescription` en `sensor.py` con `translation_key` (no asignes `_attr_name`,
   anularía la traducción) y el flag de disponibilidad adecuado.
3. Añade la clave en `strings.json`, `translations/en.json` y `translations/es.json`
   (`strings.json` y `en.json` en inglés).
4. Importes en `"EUR"`, no `"€"`: lo exige `device_class: monetary`. Cambiar la unidad de un sensor ya
   desplegado obliga a migrar estadísticas.
5. Tests y `scripts/ci.sh`.

## Probar en un Home Assistant real

1. Copia los ficheros modificados a `/config/custom_components/aqualia/` del HA de pruebas (Samba, el
   add-on de SSH o `scp`). Guarda antes una copia de la carpeta.
2. **Reinicia Home Assistant.** Recargar la entrada no basta: los módulos Python ya importados no se
   vuelven a cargar.
3. Comprueba el estado de la entrada en **Ajustes → Dispositivos y servicios → Aqualia** o por API
   (`GET /api/config/config_entries/entry?domain=aqualia`) y los sensores en **Herramientas para
   desarrolladores → Estados**.
4. Activa logs de depuración si hace falta:

   ```yaml
   logger:
     logs:
       custom_components.aqualia: debug
   ```

Evita reiniciar en bucle si el login falla: cada intento cuenta para el límite de Aqualia.

## Convenciones

- Nombres de entidad y comentarios del código en inglés; documentación, mensajes del config flow y
  notificaciones en español.
- No hay linter configurado.
- No añadas a `requirements` del manifest paquetes que ya trae Home Assistant (`requests`,
  `cryptography`…): hassfest lo rechaza.
