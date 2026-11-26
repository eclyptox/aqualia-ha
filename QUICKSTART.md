# Inicio rápido

Integración de Aqualia en Home Assistant en 5 minutos. Detalles en [README.md](README.md).

## Necesitas

- Home Assistant con [HACS](https://hacs.xyz/) instalado.
- Tu NIF y la contraseña de la [oficina virtual de Aqualia](https://oficinavirtual.aqualia.es/).

## Pasos

1. **HACS → Integraciones → ⋮ → Repositorios personalizados**: añade
   `https://github.com/eclyptox/aqualia-ha` con categoría **Integración**.
2. Busca **Aqualia**, instálala y **reinicia Home Assistant**.
3. **Ajustes → Dispositivos y servicios → Añadir integración → Aqualia**.
4. Introduce NIF (sin espacios) y contraseña.
5. Elige tu contrato en la lista. Si no aparece, introduce los códigos a mano
   ([cómo obtenerlos](README.md#cómo-obtener-los-códigos-del-contrato-solo-si-el-discovery-falla)).

Aparecerá el dispositivo **Aqualia Water Meter** con 16 sensores de consumo y facturación.

## Siguiente paso: Energy Dashboard

**Ajustes → Dashboards → Energía → Agua**: añade `sensor.aqualia_water_meter_total_consumption`.
Para ver el gasto en €, en ese mismo sensor elige **Usar un sensor de entidad** como precio y selecciona
el sensor *Precio estimado del agua*.

## Si algo falla

| Síntoma | Causa probable |
| --- | --- |
| *Credenciales o datos de contrato incorrectos* | NIF o contraseña mal escritos |
| *No se pudo conectar con Aqualia* | La API no responde o está limitando los logins (429): espera 30 min |
| Todo en `unavailable` tras actualizar HA | Versión anterior a 0.2.1: actualiza desde HACS y reinicia |
| Los valores no cambian en 2-3 días | Normal: Aqualia publica las lecturas con retraso |

Más casos en [Solución de problemas](README.md#solución-de-problemas).
