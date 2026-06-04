# Aqualia para Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?logo=homeassistantcommunitystore&logoColor=white)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![Tests](https://img.shields.io/badge/tests-152%20passed-brightgreen?logo=pytest&logoColor=white)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Integración personalizada para Home Assistant que consulta el consumo de agua de Aqualia y crea sensores nativos, incluyendo consumo acumulado, datos de facturación y precio estimado del agua compatibles con el **Energy Dashboard**.

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

**Sensores de consumo**

| Sensor | Unidad | Descripción | Se pone unavailable si… |
| --- | --- | --- | --- |
| Consumo total (índice contador) | L | Odómetro del contador. Compatible con **Energy Dashboard** | Sin datos iniciales |
| Última lectura | L | Valor de la última lectura recibida (puede tener 2-3 días de retraso) | Sin datos iniciales |
| Consumido hoy | L | Suma de lecturas fechadas hoy (0 si Aqualia aún no las envió) | Sin lecturas >7 días |
| Consumido este mes | L | Suma de lecturas del mes actual | Sin lecturas >7 días |
| Consumo diario estimado | L/d | Última lectura dividida entre los días del gap | Sin lecturas >7 días |
| Media 30 días | L/d | Promedio móvil de los últimos 30 días | Sin datos iniciales |
| Ratio frente a media | % | Consumo estimado vs media | Sin lecturas >7 días |
| Días desde última lectura | d | Días sin lectura nueva de Aqualia | Sin datos iniciales |
| Gap de lectura | d | Días que cubre la última lectura | Sin datos iniciales |
| Fecha de última lectura | timestamp | Fecha/hora de la última lectura | Sin datos iniciales |

> **Nota sobre el retraso:** Aqualia envía lecturas con 2-3 días de retraso y a veces las agrupa
> (p.ej. 3 días sin leer → una sola lectura con el triple del consumo normal). El sensor
> *Consumo diario estimado* divide el valor por el gap para corregirlo. Los sensores derivados
> (hoy, este mes, estimado, ratio) pasan a `unavailable` automáticamente si no llega ninguna
> lectura en más de 7 días, para que las automatizaciones de alerta se activen correctamente.

**Sensores de facturación**

| Sensor | Unidad | Descripción |
| --- | --- | --- |
| Última factura | € | Importe de la última factura. Atributos: `period` ("Ene-Feb / 2026"), `status` ("Pagado") |
| Vencimiento factura | timestamp | Fecha de vencimiento de la última factura (útil para automatizaciones de aviso de cobro) |
| Importe pendiente | € | Suma de importes sin pagar. 0 € si todo está al día |
| Media de facturas | € | Importe medio de las facturas disponibles (referencia bimestral) |
| Precio estimado del agua | €/m³ | Coste efectivo medio (cuota fija + variable) por m³. Usado en el Energy Dashboard para calcular el gasto en € |

> **Nota sobre el precio estimado:** no es el precio marginal por m³ de la tarifa, sino el coste real total
> (incluyendo cuotas fijas de servicio, alcantarillado, etc.) dividido entre el volumen consumido en el
> período. Es la cifra correcta para el Energy Dashboard porque refleja lo que pagas realmente por cada
> m³ de media. Se actualiza cada 12 horas. En la primera carga puede tardar unos segundos si la integración
> necesita resolver el identificador de contrato completo.

## Energy Dashboard

### Consumo de agua

El sensor **Consumo total (índice contador)** tiene `device_class: water` y `state_class: total_increasing`. Para añadirlo:

1. Ve a **Ajustes → Dashboards → Energía**.
2. En la sección **Agua** añade el sensor `sensor.aqualia_water_meter_total_consumption`.

Los atributos del sensor incluyen `days_since_reading`, `data_delayed` y `last_update_success` para saber si el valor está actualizado. Los sensores permanecen disponibles aunque la API falle temporalmente, usando el último valor conocido.

### Coste del agua (opcional)

Para que el Energy Dashboard muestre el gasto en €:

1. En la configuración del sensor de agua, haz clic en **"Precio de la energía"**.
2. Selecciona **"Usar un sensor de entidad"**.
3. Elige `sensor.aqualia_water_meter_estimated_water_price_aqualia`.

HA multiplicará automáticamente el consumo por el precio estimado y mostrará el coste acumulado en €.

## Notificaciones de nueva factura

Cuando la integración detecta que ha llegado una factura nueva (el período cambia respecto al último conocido), hace dos cosas automáticamente:

1. **Notificación persistente en HA**: Aparece en el panel de notificaciones (icono campana) con el período, importe y fecha de vencimiento.

2. **Evento de Home Assistant `aqualia_new_invoice`**: Puedes usarlo en automatizaciones para recibir la notificación donde quieras (móvil, Telegram, etc.).

**Payload del evento:**

| Campo | Tipo | Ejemplo |
| --- | --- | --- |
| `period` | string | `"Mar-Abr / 2026"` |
| `amount` | float | `52.18` |
| `due_date` | ISO 8601 | `"2026-05-01T00:00:00+00:00"` |

**Ejemplo de automatización (notificación móvil):**

```yaml
automation:
  alias: "Aviso nueva factura Aqualia"
  trigger:
    platform: event
    event_type: aqualia_new_invoice
  action:
    service: notify.mobile_app_tu_telefono
    data:
      title: "💧 Nueva factura Aqualia"
      message: >
        Período: {{ trigger.event.data.period }}
        Importe: {{ trigger.event.data.amount }} €
```

> **Nota:** La detección se hace cada 12 horas (intervalo de refresco de facturas). No se genera notificación en el primer arranque, solo cuando se detecta un cambio real de período.

## Notas técnicas

- Usa `DataUpdateCoordinator` con llamadas HTTP en executor (cliente `requests` síncrono).
- El token JWT se renueva automáticamente antes de expirar (margen de 5 minutos).
- Las lecturas de Aqualia pueden llegar con retraso y agrupadas. `daily_normalized` divide el valor por los días del gap para normalizar.
- Si la API devuelve 401, se fuerza un nuevo login y se reintenta una vez.
- Los sensores con datos derivados pasan a `unavailable` tras 7 días sin lectura, lo que permite crear automatizaciones de alerta con el trigger `state → unavailable`.
- Los sensores de consumo y el acumulado **no pasan a `unavailable` por fallos puntuales de la API**: conservan el último valor conocido y añaden el atributo `api_error` si hay un error activo.
- Las facturas se consultan cada 12 horas (endpoint `/invoice/v1/api/invoice/Invoice/GetList`). Si el config entry no tiene los campos del `ContractIdentifier` completo (instalaciones anteriores), el coordinator los resuelve automáticamente desde `GetUserLinkedContracts` sin necesidad de reconfigurar.
- El precio estimado (€/m³) se calcula como: `media_facturas / (media_diaria_L × días_período / 1000)`, donde el período bimestral se estima a partir de las fechas de emisión de las facturas disponibles.

## Repositorio legacy

La carpeta `aqualia/` conserva el add-on MQTT original. No es necesaria para la instalación recomendada.
