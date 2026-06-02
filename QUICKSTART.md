# Quick Start - Aqualia Water Consumption Addon

## Pasos rápidos (5 minutos)

### 1. Obtener datos del contrato

1. Entra en https://oficinavirtual.aqualia.es/
2. Abre DevTools (F12)
3. Ve a la pestaña **Network**
4. Busca la request **GetContractConsumptionCurve** (POST)
5. Haz clic → **Payload** → copia estos valores:
   - `Contract.CacCode` → **cac_code**
   - `Contract.ContractCode` → **contract_code**
   - `Contract.InstallationCode` → **installation_code**
   - `Contract.ContractNumber` → **contract_number**

### 2. Instalar addon en Home Assistant

1. **Ajustes** → **Complementos** → Tienda (⋮) → **Repositorios**
2. Añade: `https://github.com/eclyptox/aqualia-ha-addon`
3. Busca "Aqualia" → **Instalar**

### 3. Configurar

1. Haz clic en **Configurar**
2. Rellena:
   - **nif**: tu NIF sin espacios
   - **password**: tu contraseña de Aqualia
   - Pega los 4 datos del contrato
   - Poll interval: 60 (minutos)
   - MQTT host: `core-mosquitto`

3. **Guardar**

### 4. Arrancar

1. **Encender** el addon
2. Abre **Logs** para verificar

Deberías ver: `Última lectura: 250L` (o similar)

### 5. Ver datos en HA

Abre **Desarrollador** → **Estados** y busca `sensor.aqualia_*`

### 6. (Opcional) Alertas

Copia una automatización de [DOCS.md](DOCS.md) a **Automaciones**.

---

## Troubleshooting rápido

| Problema | Solución |
|----------|----------|
| Login falló | Revisa NIF/password |
| MQTT no conectado | ¿Está encendido el addon Mosquitto? |
| Sin datos en HA | Espera 1-2 minutos y recarga los estados |
| Sensor unavailable | Revisa los logs del addon |

---

**¡Listo!** 🎉 Ahora tienes tu consumo de agua en Home Assistant.
