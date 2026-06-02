# Aqualia para Home Assistant

Integracion personalizada para Home Assistant que consulta el consumo de agua de Aqualia y crea sensores nativos, sin MQTT ni add-on intermedio.

## Por que integracion nativa

- No requiere Mosquitto ni credenciales MQTT.
- Se configura desde **Ajustes -> Dispositivos y servicios**.
- Usa entidades nativas de Home Assistant con actualizacion periodica.
- Reduce puntos de fallo frente al add-on MQTT.

El add-on MQTT antiguo sigue en `aqualia/`, pero la ruta recomendada es `custom_components/aqualia`.

## Sensores

La integracion crea estas entidades:

| Sensor | Unidad | Descripcion |
| --- | --- | --- |
| Ultima lectura | L | Valor de la ultima lectura recibida |
| Consumo diario normalizado | L/d | Consumo dividido por el gap de lectura |
| Media 30 dias | L/d | Promedio movil de los ultimos 30 dias |
| Ratio frente a media | % | Consumo normalizado frente a la media |
| Total mensual | L | Suma de lecturas del mes actual |
| Dias desde ultima lectura | d | Dias sin una lectura nueva |
| Gap de lectura | d | Dias cubiertos por la ultima lectura |
| Fecha de ultima lectura | timestamp | Fecha/hora de la ultima lectura |

## Instalacion

1. Copia `custom_components/aqualia` dentro de la carpeta `custom_components` de tu Home Assistant.
2. Reinicia Home Assistant.
3. Ve a **Ajustes -> Dispositivos y servicios -> Anadir integracion**.
4. Busca **Aqualia**.
5. Introduce tus credenciales y datos del contrato.

## Datos necesarios

| Campo | Descripcion | Ejemplo |
| --- | --- | --- |
| `nif` | Tu NIF sin espacios | `12345678A` |
| `password` | Contrasena de Aqualia | `MiContrasena123` |
| `cac_code` | CAC Code del contrato | `6565462` |
| `contract_code` | Contract Code | `38692` |
| `installation_code` | Installation Code | `10302` |
| `contract_number` | Numero completo de contrato | `10302-1/1-047339` |
| `poll_interval_minutes` | Intervalo de consulta | `60` |
| `days_back` | Historico a consultar | `60` |

## Como encontrar los datos del contrato

1. Entra en https://oficinavirtual.aqualia.es/.
2. Abre DevTools del navegador.
3. En **Network**, busca la peticion `GetContractConsumptionCurve`.
4. En el payload copia:
   - `Contract.CacCode`
   - `Contract.ContractCode`
   - `Contract.InstallationCode`
   - `Contract.ContractNumber`

## Notas tecnicas

- La integracion usa `DataUpdateCoordinator` y ejecuta las llamadas HTTP en executor.
- El token JWT se mantiene en memoria y se renueva automaticamente antes de expirar.
- Las lecturas de Aqualia pueden llegar con retraso y agrupadas; `daily_normalized` divide el valor por los dias del gap.
- Si la API devuelve 401, se fuerza un nuevo login y se reintenta una vez.

## Desarrollo

Validar sintaxis:

```bash
python3 -c "import pathlib; [compile(p.read_text(), str(p), 'exec') for p in pathlib.Path('custom_components/aqualia').rglob('*.py')]"
```

La carpeta `aqualia/` conserva el add-on MQTT legacy, pero no es necesaria para la instalacion recomendada.
