# 📑 Índice del Proyecto - Aqualia HA Addon

## 🎯 Resumen Ejecutivo

**Addon de Home Assistant completamente desarrollado** para integrar el consumo de agua de Aqualia.

- ✅ **Código:** 6 módulos Python (~765 líneas)
- ✅ **Docker:** Imagen multiarch funcional (113 MB)
- ✅ **MQTT:** 8 sensores con autodiscovery
- ✅ **Documentación:** 1000+ líneas

---

## 📂 Estructura de Carpetas

```
aqualia-ha-addon/                    # Raíz del proyecto
│
├── aqualia/                          # 📦 Carpeta del ADDON
│   ├── config.yaml                  # Configuración del addon para HA
│   ├── Dockerfile                   # Construcción multiarch (amd64, aarch64, armv7)
│   ├── run.sh                        # Script de entrada
│   ├── requirements.txt              # Dependencias Python
│   │
│   └── app/                          # 🐍 Código Python
│       ├── main.py                  # Bucle principal (~100 líneas)
│       ├── config_loader.py         # Lee options.json (~80 líneas)
│       ├── aqualia_client.py        # Cliente API (~170 líneas)
│       ├── token_cache.py           # Caché JWT (~75 líneas)
│       ├── consumption_parser.py    # Análisis de lecturas (~140 líneas)
│       └── ha_mqtt.py               # MQTT Discovery (~200 líneas)
│
└── 📚 DOCUMENTACIÓN
    ├── README.md                    # Guía de instalación (340 líneas)
    ├── QUICKSTART.md                # Setup en 5 minutos (50 líneas)
    ├── DOCS.md                      # Documentación técnica (480 líneas)
    ├── DEVELOPMENT.md               # Guía para desarrolladores (150 líneas)
    ├── BUILD_SUMMARY.md             # Resumen de construcción
    ├── GITHUB_SETUP.md              # Publicar en GitHub
    ├── INDEX.md                     # Este archivo
    └── .gitignore                   # Ficheros a ignorar

```

---

## 📖 Guía de Lectura

### Para instaladores (usuarios)

1. **START HERE:** [QUICKSTART.md](QUICKSTART.md) ⭐
   - Setup en 5 minutos
   - Tablas rápidas
   - Troubleshooting básico

2. **Instalación completa:** [README.md](README.md)
   - Requisitos previos
   - Paso a paso
   - Cómo encontrar datos del contrato
   - Troubleshooting detallado

3. **Automatizaciones:** [DOCS.md](DOCS.md) (sección "Automatizaciones")
   - 3 YAML listos para copiar
   - Tarjeta Lovelace

### Para desarrolladores

1. **Ver cómo funciona:** [DOCS.md](DOCS.md) (sección "Arquitectura")
   - Flujo de ejecución
   - Gestión de token
   - MQTT Discovery

2. **Modificar código:** [DEVELOPMENT.md](DEVELOPMENT.md)
   - Setup local
   - Testing
   - Build Docker
   - Guías de cambios comunes

3. **Publicar:** [GITHUB_SETUP.md](GITHUB_SETUP.md)
   - Crear repo
   - CI/CD
   - Releases

### Resumen técnico: [BUILD_SUMMARY.md](BUILD_SUMMARY.md)

---

## 🐍 Módulos Python

| Archivo | Líneas | Responsabilidad |
|---------|--------|-----------------|
| **main.py** | 100 | Bucle principal, orquestación |
| **config_loader.py** | 80 | Lee options.json del addon |
| **aqualia_client.py** | 170 | Cliente HTTP, autenticación, API |
| **token_cache.py** | 75 | Caché JWT persistente |
| **consumption_parser.py** | 140 | Análisis de lecturas, métricas |
| **ha_mqtt.py** | 200 | MQTT Discovery, publicación |

**Total:** ~765 líneas de código funcional

---

## 🔌 Entidades MQTT (8)

El addon publica estas entidades automáticamente en Home Assistant:

| Sensor | Topic | Unidad |
|--------|-------|--------|
| Última lectura | `aqualia/sensor/last_value` | L |
| Consumo normalizado | `aqualia/sensor/daily_normalized` | L/d |
| Media 30 días | `aqualia/sensor/avg_30d` | L/d |
| Ratio vs media | `aqualia/sensor/ratio_vs_avg` | % |
| Total mensual | `aqualia/sensor/monthly_total` | L |
| Días sin lectura | `aqualia/sensor/days_since_reading` | d |
| Gap de lectura | `aqualia/sensor/reading_gap` | d |
| Fecha última | `aqualia/sensor/last_reading_date` | ISO |

---

## ⚙️ Configuración

**Parámetros requeridos:**
- NIF (usuario Aqualia)
- Contraseña
- CAC Code, Contract Code, Installation Code, Contract Number

**Parámetros opcionales:**
- Poll interval: 60 minutos (min: 5, max: 1440)
- Días históricos: 60 días (min: 7, max: 365)
- MQTT host/puerto/credenciales

Ver [README.md](README.md) para detalles.

---

## 🐳 Docker

**Imagen construida:**
- Tamaño: 113 MB
- Arquitecturas: amd64, aarch64, armv7
- Base: ghcr.io/home-assistant/{arch}-base:3.19
- Status: ✅ Probada y funcional

**Build:**
```bash
cd aqualia/
docker build -t aqualia-ha-addon:latest .
```

---

## 🚀 Quick Start

```bash
# 1. Lee esto (5 min)
cat QUICKSTART.md

# 2. Obtén datos del contrato (2 min)
# Ver QUICKSTART.md

# 3. Instala en HA
# Ajustes → Complementos → Tienda → Repositorios
# Añade: https://github.com/tu-usuario/aqualia-ha-addon

# 4. Configura y arranca
# El addon publicará en MQTT automáticamente
```

---

## 📋 Funcionalidades

### ✅ Implementado

- Login automático
- Caché JWT persistente
- Renovación automática de token
- Reintentos exponenciales (5s, 15s, 60s)
- Análisis de lecturas acumuladas
- 6 métricas inteligentes
- MQTT Discovery
- 8 sensores automáticos
- Logging estructurado
- Manejo robusto de errores

### 📝 Configuración

- Lectura de options.json
- Validación de parámetros
- MQTT con/sin autenticación
- Intervalo flexible

### 🔒 Seguridad

- NIF/password en variables locales
- Token con expiración
- Caché en `/share/` (seguro en HA)
- Sin credenciales en logs

---

## 📊 Estadísticas

| Métrica | Valor |
|---------|-------|
| Código Python | ~765 líneas |
| Documentación | ~1000 líneas |
| Módulos | 6 |
| Funciones/Métodos | ~45 |
| Entidades MQTT | 8 |
| Automatizaciones ejemplo | 3 |
| Archivos total | 15 |
| Tamaño Docker | 113 MB |

---

## 🎓 Cómo aprender el código

### Principiante

1. Lee [README.md](README.md) para entender qué hace
2. Lee [QUICKSTART.md](QUICKSTART.md) para ver cómo se usa
3. Mira `aqualia/config.yaml` para ver la configuración

### Intermedio

1. Lee [DOCS.md](DOCS.md) "Arquitectura" sección
2. Abre `aqualia/app/main.py` para ver el bucle
3. Explora los módulos:
   - config_loader.py: cómo se lee la config
   - token_cache.py: cómo se guarda el JWT
   - aqualia_client.py: cómo se autentica en Aqualia

### Avanzado

1. Lee [DEVELOPMENT.md](DEVELOPMENT.md)
2. Examina todos los módulos Python
3. Mira el Dockerfile para entender el build
4. Lee [GITHUB_SETUP.md](GITHUB_SETUP.md) para CI/CD

---

## 🔗 Enlaces útiles

### Home Assistant
- [Addon Docs](https://developers.home-assistant.io/docs/add-ons/)
- [MQTT Discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery)
- [Lovelace](https://www.home-assistant.io/lovelace/)

### Python
- [Requests](https://requests.readthedocs.io/)
- [Paho MQTT](https://www.eclipse.org/paho/client-python/)

### API Aqualia
- [Oficina Virtual](https://oficinavirtual.aqualia.es/)

---

## ❓ Preguntas frecuentes

**¿Cómo instalo el addon?**
→ Ver [QUICKSTART.md](QUICKSTART.md) o [README.md](README.md)

**¿Cómo encuentro mis datos del contrato?**
→ Ver [README.md](README.md) sección "Encontrar los datos"

**¿Qué métrica debo usar para alertas?**
→ Ver [DOCS.md](DOCS.md) sección "Automatizaciones"

**¿Puedo modificar el código?**
→ Sí, ver [DEVELOPMENT.md](DEVELOPMENT.md)

**¿Cómo publico mi propia versión?**
→ Ver [GITHUB_SETUP.md](GITHUB_SETUP.md)

---

## 📞 Soporte

Si tienes problemas:

1. Mira la sección **Troubleshooting** en [README.md](README.md)
2. Revisa los logs del addon: Ajustes → Complementos → Aqualia → Logs
3. Abre un issue en GitHub con logs completos

---

## 📄 Licencia

MIT - Ver archivo `LICENSE` (crear si publicas en GitHub)

---

**Proyecto completado:** 2026-05-15  
**Status:** ✅ Listo para usar y distribuir
