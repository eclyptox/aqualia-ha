ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.19
FROM ${BUILD_FROM}

# Instalar Python y dependencias
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-requests \
    py3-paho-mqtt

# Crear directorio de trabajo
WORKDIR /app

# Copiar requirements
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copiar aplicación
COPY app/ ./app/
COPY run.sh .

# Permisos de ejecución
RUN chmod +x run.sh

# Entrypoint
CMD [ "./run.sh" ]
