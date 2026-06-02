# Documentación Técnica - Aqualia Water Consumption Addon

## Arquitectura del Addon

```
aqualia/
├── config.yaml              # Manifiesto del addon (HA lo lee)
├── Dockerfile               # Construcción del contenedor
├── run.sh                   # Entrypoint (inicia main.py)
├── requirements.txt         # Dependencias Python (requests, paho-mqtt)
└── app/
    ├── main.py              # Bucle principal
    ├── config_loader.py     # Lee options.json del addon
    ├── aqualia_client.py    # Cliente API (auth + consumo)
    ├── token_cache.py       # Caché JWT persistente
    ├── consumption_parser.py # Análisis de lecturas
    └── ha_mqtt.py           # MQTT Discovery para HA
```

## Flujo de ejecución

```
1. main.py inicia
   ├─ Carga config desde /data/options.json (config_loader.py)
   ├─ Crea cliente Aqualia (aqualia_client.py)
   └─ Conecta a MQTT broker (ha_mqtt.py)

2. Bucle principal cada poll_interval_minutes:
   ├─ Obtiene lecturas: aqualia.get_consumption()
   │  ├─ Valida token (renueva si expirado)
   │  ├─ Fetch XSRF-TOKEN desde oficinavirtual.aqualia.es
   │  └─ POST al endpoint GetContractConsumptionCurve
   │
   ├─ Procesa lecturas: ConsumptionParser(readings)
   │  ├─ Ordena por fecha
   │  ├─ Calcula daily_normalized (divide por gap)
   │  ├─ Calcula avg_daily_30d (media móvil)
   │  ├─ Calcula ratio_vs_avg (%)
   │  └─ Calcula otros metrics
   │
   └─ Publica en MQTT: mqtt.publish_metrics(metrics)
      ├─ Config topics (MQTT Discovery)
      └─ State topics
```

## Gestión del Token JWT

### TokenCache (`app/token_cache.py`)

- **Ubicación:** `/share/aqualia_token_cache.json` (persiste entre reinicios)
- **Formato:**
  ```json
  {
    "token": "eyJhbGciOiJIUzI1NiIs...",
    "expires_at": "2026-05-15T12:34:56.789012"
  }
  ```

### Renovación automática

1. Al arrancar, `_ensure_token()` busca en caché
2. Si no existe o está expirado, hace login
3. Si login devuelve 401 en `get_consumption()`, limpia caché y reinicia
4. Margen de seguridad: -5 minutos antes de expiración

### Autenticación (flujo)

```
GET /oficinavirtual.aqualia.es/
├─ Response incluye cookie XSRF-TOKEN
└─ Se guarda en session.cookies

POST /ofcvirtual/auth/v1/api/auth/Auth/Login
├─ Header X-XSRF-TOKEN: <cookie obtenida>
├─ Body: {LoginType: 1, User: NIF, Password: pass}
└─ Response: {Token: "Bearer JWT", ...}
```

## Análisis de Lecturas (ConsumptionParser)

### El problema: lecturas acumuladas con gaps

Aqualia envía **lecturas diarias** pero pueden:
- Llegar **2-3 días después**
- Estar **acumuladas** (si no leen 3 días, 1 lectura con triple consumo)

### Solución: normalización

```
reading_gap_days = diferencia de fechas entre esta lectura y la anterior
daily_normalized = last_value / reading_gap_days

Ejemplo:
- Lectura 1: 100L (1 día)
- Lectura 2: 300L (3 días después) → normalizado = 300/3 = 100L/día
```

### Métricas calculadas

| Métrica | Fórmula | Ejemplo |
|---------|---------|---------|
| `last_value` | último valor leído | 250 L |
| `daily_normalized` | `last_value / gap_days` | 83.33 L/d |
| `avg_daily_30d` | media de valores normalizados (30d) | 80.5 L/d |
| `ratio_vs_avg` | `(daily_normalized / avg_30d) * 100` | 103.5 % |
| `monthly_total` | suma de lecturas del mes actual | 2420 L |
| `days_since_reading` | días desde última lectura | 3 |
| `reading_gap_days` | días que cubre última lectura | 3 |

## MQTT Discovery

### Topics de configuración

```
homeassistant/sensor/aqualia/{entity_id}/config

Ejemplo:
homeassistant/sensor/aqualia/daily_normalized/config
```

### Payload de discovery

```json
{
  "unique_id": "aqualia_daily_normalized",
  "name": "Water Meter - Daily Normalized Consumption",
  "state_topic": "aqualia/sensor/daily_normalized",
  "unit_of_measurement": "L/d",
  "device_class": "water",
  "state_class": "measurement",
  "icon": "mdi:water-percent",
  "device": {
    "identifiers": ["aqualia_water"],
    "name": "Aqualia Water Meter",
    "manufacturer": "Aqualia",
    "model": "Water Meter"
  }
}
```

### Topics de estado

```
aqualia/sensor/last_value                    # L
aqualia/sensor/daily_normalized              # L/d (número, 2 decimales)
aqualia/sensor/avg_30d                       # L/d (número, 2 decimales)
aqualia/sensor/ratio_vs_avg                  # % (número, 1 decimal)
aqualia/sensor/monthly_total                 # L (número entero)
aqualia/sensor/days_since_reading            # d (número entero)
aqualia/sensor/reading_gap                   # d (número entero)
aqualia/sensor/last_reading_date             # ISO string
```

En caso de error: todos los topics reciben `"unavailable"`

## Automatizaciones recomendadas

### 1. Alerta de consumo elevado

Triggers cuando:
- `ratio_vs_avg > 150%` AND
- `reading_gap_days < 3` AND
- `days_since_reading < 5`

Copia esto a **Automations** en HA:

```yaml
alias: "🚨 Aqualia - Consumo elevado"
description: "Alerta si consumo > 150% de media"
trigger:
  - platform: numeric_state
    entity_id: sensor.aqualia_ratio_vs_avg
    above: 150
condition:
  - condition: numeric_state
    entity_id: sensor.aqualia_reading_gap_days
    below: 3
  - condition: numeric_state
    entity_id: sensor.aqualia_days_since_reading
    below: 5
action:
  - service: notify.notify
    data:
      title: "⚠️ Consumo de agua anómalo"
      message: |
        Consumo normalizado: {{ state_attr('sensor.aqualia_daily_normalized', '') }} L/d
        Media 30d: {{ state_attr('sensor.aqualia_avg_30d', '') }} L/d
        Ratio: {{ states('sensor.aqualia_ratio_vs_avg') }}%
mode: single
```

### 2. Alerta de sin lecturas

Triggers cuando no hay lectura nueva en >5 días:

```yaml
alias: "📊 Aqualia - Sin lecturas"
description: "Alerta si más de 5 días sin lectura"
trigger:
  - platform: numeric_state
    entity_id: sensor.aqualia_days_since_reading
    above: 5
action:
  - service: notify.notify
    data:
      title: "⚠️ Sin lecturas de agua"
      message: "No hay lecturas hace {{ states('sensor.aqualia_days_since_reading') }} días. Última lectura: {{ states('sensor.aqualia_last_reading_date') }}"
mode: single
```

### 3. Alerta de error de API

Triggers cuando el sensor principal no está disponible >4h:

```yaml
alias: "❌ Aqualia - Error de API"
description: "Alerta si el addon falla"
trigger:
  - platform: state
    entity_id: sensor.aqualia_last_value
    to: "unavailable"
    for:
      hours: 4
action:
  - service: notify.notify
    data:
      title: "❌ Error del addon Aqualia"
      message: "El addon no puede conectar con la API. Revisa los logs del addon."
mode: single
```

### 4. Tarjeta Lovelace personalizada

Copia esto a una tarjeta **Manual YAML** en tu dashboard:

```yaml
type: custom:stack-in-card
cards:
  - type: entities
    title: "💧 Aqualia - Agua"
    show_header_toggle: false
    entities:
      - entity: sensor.aqualia_daily_normalized
        name: "Hoy (normalizado)"
      - entity: sensor.aqualia_avg_30d
        name: "Promedio 30 días"
      - entity: sensor.aqualia_ratio_vs_avg
        name: "Ratio vs media"
        icon: mdi:percent
      - entity: sensor.aqualia_monthly_total
        name: "Total mes"
      - entity: sensor.aqualia_days_since_reading
        name: "Días sin lectura"
        icon: mdi:calendar-clock
      - entity: sensor.aqualia_last_reading_date
        name: "Última lectura"
        icon: mdi:calendar-check

  - type: history-stats
    title: "Consumo últimas 24h"
    entities:
      - sensor.aqualia_daily_normalized
    period_keys:
      - bar
    stat_period_duration: 24h

  - type: custom:gauge-card
    entity: sensor.aqualia_ratio_vs_avg
    name: "Ratio vs media"
    min: 0
    max: 200
    severity:
      green: 0
      yellow: 120
      red: 150
```

## Debugging

### Acceder a los logs del addon

Home Assistant → Ajustes → Complementos → Aqualia → **Logs**

### Habilitar debug logging (si fuera necesario)

Modifica `app/main.py`:
```python
logging.basicConfig(
    level=logging.DEBUG,  # Cambiar INFO a DEBUG
    ...
)
```

### Ver topics MQTT

```bash
mosquitto_sub -h localhost -t "aqualia/#" -v
```

### Verificar JWT en caché

```bash
cat /share/aqualia_token_cache.json | jq .
```

## Requisitos de construcción Docker

```dockerfile
FROM ghcr.io/home-assistant/{amd64|aarch64|armv7}-base:3.19
- Python 3.11
- requests 2.31.0
- paho-mqtt 1.6.1
```

Test de construcción:
```bash
cd aqualia/
docker build -t aqualia-ha-addon:latest .
```

## Configuración de permisos en MQTT

Si tu Mosquitto require autenticación:

1. Crea usuario en Mosquitto:
   ```bash
   mosquitto_passwd -c /mosquitto/config/passwd aqualia
   ```

2. Configura el addon con ese usuario/contraseña

3. Asegúrate de que el usuario tiene permisos:
   ```
   user aqualia
   topic write aqualia/#
   topic write homeassistant/sensor/aqualia/#
   ```

## Performance y escalabilidad

- **Consumo de RAM:** ~50-100 MB
- **CPU:** Mínimo, principalmente en espera
- **Ancho de banda:** ~50-100 KB por consulta
- **Almacenamiento:** ~1 KB (token cache)

## Solución de problemas comunes

| Error | Causa | Solución |
|-------|-------|----------|
| `Login falló después de reintentos` | NIF/pass incorrecto | Verifica credenciales en config |
| `No se encontró XSRF-TOKEN` | API de Aqualia cambió | Reporta issue en GitHub |
| `401 Unauthorized` | Token expirado | Se renueva automáticamente |
| `Connection refused (MQTT)` | Mosquitto no activo | Inicia Mosquitto addon |
| `Sensor unavailable` | Error en get_consumption() | Revisa logs, reinicia addon |

## Licencia

MIT
