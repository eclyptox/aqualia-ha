# Referencia de la API de Aqualia

Documentación de la API no oficial de la oficina virtual de Aqualia tal y como la usa
`custom_components/aqualia/api.py`. Aqualia no la publica: todo sale de observar la web
`https://oficinavirtual.aqualia.es/` y puede cambiar sin aviso (como pasó con el login en noviembre
de 2026).

## Base y cabeceras

Base: `https://oficinavirtualapi.aqualia.es/ofcvirtual`

Todas las peticiones llevan estas cabeceras; sin ellas la API las rechaza:

| Cabecera | Valor |
| --- | --- |
| `Application-Id` | `1` |
| `Country` | `34` |
| `Origin` | `https://oficinavirtual.aqualia.es` |
| `Referer` | `https://oficinavirtual.aqualia.es/` |
| `Accept-Language` | `es-es` |
| `Content-Type` | `application/json; charset=UTF-8` |
| `X-Requested-With` | `XMLHttpRequest` |

Las peticiones autenticadas añaden `Authorization: Bearer <Token>`.

Las fechas se envían en ISO 8601 UTC con `Z` (`2026-11-26T06:00:00Z`).

## Login cifrado

`POST /auth/v1/api/auth/Auth/Login`

Desde noviembre de 2026 el login rechaza las credenciales en claro con
`500 "The User parameter does not meet the encryption criteria."`. La web cifra los campos así, y la
integración hace lo mismo:

1. **Clave pública.** Se lee de la configuración de la web,
   `https://oficinavirtual.aqualia.es/config/config.json`, campo `pkEnc`: base64 de un PEM
   `-----BEGIN PUBLIC KEY-----` (RSA 2048). No se escribe en el código para sobrevivir a una
   rotación; se cachea por instancia del cliente.
2. **Clave de sesión.** 32 bytes aleatorios (clave AES-256).
3. **Cuerpo.** Cada campo sensible se cifra con RSA-OAEP (MGF1 y hash SHA-256, sin etiqueta) y se
   envía en base64:

   ```json
   {
     "LoginType": 1,
     "User": "<RSA-OAEP(nif)>",
     "Password": "<RSA-OAEP(contraseña)>",
     "SessionKey": "<RSA-OAEP(clave AES de 32 bytes)>"
   }
   ```

4. **Respuesta.** `200 {"Payload": "<base64>"}`. El payload es `iv (12 bytes) || ciphertext+tag`,
   cifrado con AES-GCM usando la clave de sesión. Descifrado, es un JSON:

   | Campo | Notas |
   | --- | --- |
   | `ResponseCode` | `"00001"` = correcto. `"99980"` = usuario o contraseña incorrectos |
   | `Token` | JWT para el resto de peticiones. Solo presente si el login es correcto |
   | `TokenExpirationDate` | Caducidad del token; la integración usa la menor entre esta y 8 h |
   | `Name`, `Email`, `Phone`… | Datos del titular (no se usan) |

La web consulta antes `GET /auth/v1/api/auth/Auth/GetCSRFToken` y pasa un reCAPTCHA v3
(`/auth/v1/api/auth/Auth/Recaptcha`), pero ninguno de los dos es necesario para que el login funcione.

### Errores del login

| Respuesta | Tratamiento en la integración |
| --- | --- |
| `401` / `403` | `AqualiaAuthError` → reautenticación en HA |
| `ResponseCode 99980` sin `Token` | `AqualiaAuthError` → reautenticación en HA |
| Otro `ResponseCode` sin `Token` | `AqualiaApiError` (transitorio, HA reintenta) |
| `429 Too Many Requests` | `AqualiaRateLimitError`: sin reintentos y pausa de 30 min por NIF (o `Retry-After`) |
| Error de red / 5xx | Hasta 3 intentos con esperas de 5 y 15 s |

El límite de `429` parece aplicarse **por cuenta**, no por IP. Los reintentos de arranque de Home
Assistant (cada 1-2 min) bastaban para mantenerlo activo de forma indefinida; por eso la pausa vive a
nivel de módulo y sobrevive a que HA cree un cliente nuevo en cada reintento.

## Contratos

`GET /contract/v1/api/contract/Contract/GetUserLinkedContracts` (autenticado)

Devuelve `ContractDetails[]`. De cada elemento se usan `ContractInfo` (`CacCode`, `ContractCode`,
`InstallationCode`, `ContractNumber`, `MunicipalityCode`, `EntryDate`, `ContractStatusCode`,
`ContractStatus`) y `SupplyAddress` para mostrar el selector del config flow.

Si responde `401`/`403`/`404`/`405` o una lista vacía, el config flow pasa a pedir los códigos a mano.

## Consumo

`POST /meter/v1/api/meter/Meter/GetContractConsumptionCurve` (autenticado)

```json
{
  "DateFrom": "2026-09-27T06:00:00Z",
  "DateTo": "2026-11-26T06:00:00Z",
  "Contract": {
    "CacCode": 0,
    "ContractCode": 0,
    "InstallationCode": 0,
    "ContractNumber": "00000-1/1-000000"
  }
}
```

La respuesta puede ser la lista de lecturas directamente o un objeto con `ConsumptionCurves` o `Data`.
Campos de cada lectura:

| Campo | Significado |
| --- | --- |
| `DateTimeConsumptionCurve` | Fecha de la lectura (ISO) |
| `ConsumptionValue` | Litros consumidos en el intervalo |
| `ReadingIndex` | Odómetro del contador en litros. A veces llega vacío o `0`: se trata como "sin dato", nunca como 0 |

Las lecturas llegan con 2-3 días de retraso y a veces agrupadas (una lectura cubre varios días).

## Facturas

`POST /invoice/v1/api/invoice/Invoice/GetList` (autenticado, timeout de 30 s)

Necesita el `ContractIdentifier` completo, no solo los 4 campos del contrato:

```json
{
  "StartDate": "2024-11-26T06:00:00Z",
  "EndDate": "2026-11-26T06:00:00Z",
  "ContractIdentifier": {
    "CacCode": 0,
    "ContractCode": 0,
    "ContractNumber": "00000-1/1-000000",
    "InstallationCode": 0,
    "MunicipalityCode": "00000",
    "EntryDate": "…",
    "ContractStatusCode": 0,
    "ContractStatus": "…",
    "styleClass": ""
  },
  "HasDebt": null
}
```

Respuesta: `PaymentDocuments[]`, de los que se usan `IssueDate`, `DueDate`, `Period`,
`TotalAmount`, `PendingAmount` y `Status`. Importes y fechas llegan a veces a `null` o en formatos
no ISO; se descartan en vez de propagar el error.

## Respuestas `401` en peticiones autenticadas

Ante un `401` el cliente borra el token, vuelve a iniciar sesión y reintenta **una** vez. Un segundo
`401`, o un `403`, se convierte en `AqualiaAuthError`.
