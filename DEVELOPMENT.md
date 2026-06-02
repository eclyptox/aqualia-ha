# Guía de Desarrollo - Aqualia Addon

## Setup local

### Requisitos

- Python 3.11+
- Docker
- Home Assistant (para testing con MQTT real)

### Instalar dependencias

```bash
cd aqualia/
pip3 install -r requirements.txt
```

### Estructura de módulos

```
app/
├── config_loader.py         # Lee options.json del addon
├── aqualia_client.py        # Cliente API (login + consumo)
├── token_cache.py           # Caché JWT persistente
├── consumption_parser.py    # Análisis de lecturas
├── ha_mqtt.py               # MQTT Discovery
└── main.py                  # Bucle principal
```

### Dependencias

- **requests**: cliente HTTP para API de Aqualia
- **paho-mqtt**: cliente MQTT para publicar a HA
- **json, logging, datetime**: librerías estándar

## Testing

### Test unitario básico

```bash
python3 -m app.token_cache
python3 -m app.consumption_parser
```

### Test con MQTT local

```bash
# En una terminal, inicia Mosquitto
docker run -it --rm -p 1883:1883 eclipse-mosquitto:latest

# En otra, ejecuta el addon (requiere configuración)
python3 app/main.py
```

### Ver topics MQTT

```bash
mosquitto_sub -h localhost -t "aqualia/#" -v
```

## Construir imagen Docker

### Para amd64 (dev)

```bash
cd aqualia/
docker build -t aqualia-ha-addon:latest .
docker images aqualia-ha-addon
```

### Para múltiples arquitecturas (buildx)

```bash
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  -t username/aqualia-ha-addon:latest \
  ./aqualia/
```

## Modificar código

### Cambios en la autenticación

Edita `app/aqualia_client.py`:
- `_fetch_xsrf_token()`: cómo obtener XSRF-TOKEN
- `_login_with_retries()`: lógica de login
- `_ensure_token()`: renovación automática

### Cambios en métricas

Edita `app/consumption_parser.py`:
- Añade un nuevo método `_get_metric_name()`
- Agrégalo al dict `self.metrics` en `parse()`

### Cambios en MQTT

Edita `app/ha_mqtt.py`:
- `_publish_discovery()`: añade nueva entidad
- `publish_metrics()`: publica el valor

### Cambios en configuración

Edita:
- `aqualia/config.yaml`: opción en el manifiesto
- `app/config_loader.py`: property del loader

## Debugging

### Logs detallados

```python
# En app/main.py
logging.basicConfig(level=logging.DEBUG)
```

### Modo interactivo

```python
from app.config_loader import ConfigLoader
from app.aqualia_client import AqualiaClient

config = ConfigLoader()
config.config = {
    'nif': '12345678A',
    'password': 'mypass',
    'cac_code': 6565462,
    ...
}

client = AqualiaClient(config.nif, config.password)
readings = client.get_consumption(...)
```

### Ver caché JWT

```bash
cat /share/aqualia_token_cache.json | python3 -m json.tool
```

## Versionado

- **config.yaml**: cambia `version: X.Y.Z`
- **requirements.txt**: pip freeze > requirements.txt
- **CHANGELOG**: documenta cambios

## CI/CD (si usas GitHub)

Ejemplo `.github/workflows/build.yml`:

```yaml
name: Build Docker Image
on:
  push:
    tags:
      - 'v*'

jobs:
  buildx:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: docker/setup-buildx-action@v2
      - uses: docker/build-push-action@v4
        with:
          context: ./aqualia
          platforms: linux/amd64,linux/arm64,linux/arm/v7
          tags: username/aqualia-ha-addon:${{ github.ref_name }}
          push: true
```

## Licencia

MIT
