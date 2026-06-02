# Aqualia para Home Assistant

Integración personalizada para Home Assistant que consulta el consumo de agua de Aqualia y crea sensores nativos, incluyendo un sensor acumulativo compatible con el **Energy Dashboard**.

## Instalación con HACS (recomendado)

1. En Home Assistant ve a **HACS → Integraciones → ⋮ → Repositorios personalizados**.
2. Añade `https://github.com/eclyptox/aqualia-ha` con categoría **Integración**.
3. Busca **Aqualia** en HACS e instala.
4. Reinicia Home Assistant.
5. Ve a **Ajustes → Dispositivos y servicios → Añadir integración → Aqualia**.

## Instalación manual

1. Copia `custom_components/aqualia` dentro de la carpeta `custom_components` de tu configuración de Home Assistant.
2. Reinicia Home Assistant.
3. Ve a **Ajustes → Dispositivos y servicios → Añadir integración → Aqualia**.

## Configuración

La integración usa un flujo de dos pasos:

**Paso 1 — Credenciales**

| Campo | Descripción |
| --- | --- |
| NIF | Tu NIF sin espacios (`12345678A`) |
| Contraseña | Contraseña de tu cuenta Aqualia |

**Paso 2 — Contrato**

La integración intenta descubrir tus contratos automáticamente. Si tiene éxito, aparece un selector con todos tus contratos. Si no, introduce los códigos manualmente (ver sección siguiente).

| Campo opcional | Descripción | Por defecto |
| --- | --- | --- |
| Intervalo de consulta | Minutos entre actualizaciones | 60 |
| Días de histórico | Lecturas a recuperar en el primer arranque | 60 |

## Cómo obtener los códigos del contrato (solo si el discovery falla)

1. Entra en `https://oficinavirtual.aqualia.es/`.
2. Abre DevTools del navegador (F12) → pestaña **Network**.
3. Busca la petición `GetContractConsumptionCurve`.
4. En el payload copia `Contract.CacCode`, `Contract.ContractCode`, `Contract.InstallationCode` y `Contract.ContractNumber`.

## Sensores

La integración crea estas entidades bajo el dispositivo **Aqualia Water Meter**:

| Sensor | Unidad | Descripción |
| --- | --- | --- |
| Consumo total | L | Acumulado histórico. Compatible con **Energy Dashboard** |
| Última lectura | L | Valor de la última lectura recibida |
| Consumo diario normalizado | L/d | Consumo dividido entre los días del gap |
| Media 30 días | L/d | Promedio móvil de los últimos 30 días |
| Ratio frente a media | % | Consumo normalizado vs media |
| Total mensual | L | Suma de lecturas del mes actual |
| Días desde última lectura | d | Días sin lectura nueva |
| Gap de lectura | d | Días que cubre la última lectura |
| Fecha de última lectura | timestamp | Fecha/hora de la última lectura |

## Energy Dashboard

El sensor **Consumo total** tiene `device_class: water` y `state_class: total_increasing`. Para añadirlo:

1. Ve a **Ajustes → Dashboards → Energía**.
2. En la sección **Agua** añade el sensor `sensor.aqualia_total_consumption`.

El total acumulado se conserva entre reinicios de Home Assistant gracias a `RestoreEntity`.

## Notas técnicas

- Usa `DataUpdateCoordinator` con llamadas HTTP en executor (cliente `requests` síncrono).
- El token JWT se renueva automáticamente antes de expirar (margen de 5 minutos).
- Las lecturas de Aqualia pueden llegar con retraso y agrupadas. `daily_normalized` divide el valor por los días del gap para normalizar.
- Si la API devuelve 401, se fuerza un nuevo login y se reintenta una vez.

## Repositorio legacy

La carpeta `aqualia/` conserva el add-on MQTT original. No es necesaria para la instalación recomendada.
