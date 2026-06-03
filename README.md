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

| Sensor | Unidad | Descripción | Se pone unavailable si… |
| --- | --- | --- | --- |
| Consumo total (índice contador) | L | Odómetro del contador. Compatible con **Energy Dashboard** | API caída |
| Última lectura | L | Valor de la última lectura recibida (puede tener 2-3 días de retraso) | API caída |
| Consumido hoy | L | Suma de lecturas fechadas hoy (0 si Aqualia aún no las envió) | Sin lecturas >7 días |
| Consumido este mes | L | Suma de lecturas del mes actual | Sin lecturas >7 días |
| Consumo diario estimado | L/d | Última lectura dividida entre los días del gap | Sin lecturas >7 días |
| Media 30 días | L/d | Promedio móvil de los últimos 30 días | API caída |
| Ratio frente a media | % | Consumo estimado vs media | Sin lecturas >7 días |
| Días desde última lectura | d | Días sin lectura nueva de Aqualia | API caída |
| Gap de lectura | d | Días que cubre la última lectura | API caída |
| Fecha de última lectura | timestamp | Fecha/hora de la última lectura | API caída |

> **Nota sobre el retraso:** Aqualia envía lecturas con 2-3 días de retraso y a veces las agrupa
> (p.ej. 3 días sin leer → una sola lectura con el triple del consumo normal). El sensor
> *Consumo diario estimado* divide el valor por el gap para corregirlo. Los sensores derivados
> (hoy, este mes, estimado, ratio) pasan a `unavailable` automáticamente si no llega ninguna
> lectura en más de 7 días, para que las automatizaciones de alerta se activen correctamente.

## Energy Dashboard

El sensor **Consumo total (índice contador)** tiene `device_class: water` y `state_class: total_increasing`. Para añadirlo:

1. Ve a **Ajustes → Dashboards → Energía**.
2. En la sección **Agua** añade el sensor `sensor.aqualia_total_consumption`.

Los atributos del sensor incluyen `days_since_reading` y `data_delayed` para saber si el valor está actualizado.

## Notas técnicas

- Usa `DataUpdateCoordinator` con llamadas HTTP en executor (cliente `requests` síncrono).
- El token JWT se renueva automáticamente antes de expirar (margen de 5 minutos).
- Las lecturas de Aqualia pueden llegar con retraso y agrupadas. `daily_normalized` divide el valor por los días del gap para normalizar.
- Si la API devuelve 401, se fuerza un nuevo login y se reintenta una vez.
- Los sensores con datos derivados pasan a `unavailable` tras 7 días sin lectura, lo que permite crear automatizaciones de alerta con el trigger `state → unavailable`.

## Repositorio legacy

La carpeta `aqualia/` conserva el add-on MQTT original. No es necesaria para la instalación recomendada.
