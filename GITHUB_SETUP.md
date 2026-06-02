# Publicar en GitHub - Aqualia Addon Repository

## Crear el repositorio

### En GitHub.com

1. **Crear nuevo repositorio**
   - Nombre: `aqualia-ha-addon`
   - Descripción: "Home Assistant addon para Aqualia water consumption"
   - Público (para que otros lo instalen)
   - Inicializar sin README (ya lo tenemos)

2. **Copiar URL**
   - HTTPS: `https://github.com/tu-usuario/aqualia-ha-addon.git`
   - SSH: `git@github.com:tu-usuario/aqualia-ha-addon.git`

### Inicializar git local

```bash
cd /home/german/Code/aqualia

# Si no es un repo aún
git init
git config user.name "Tu Nombre"
git config user.email "tu-email@example.com"

# Agregar todos los archivos
git add -A

# Commit inicial
git commit -m "Initial commit: Aqualia HA addon 1.0.0"

# Agregar remote (reemplaza URL)
git remote add origin https://github.com/tu-usuario/aqualia-ha-addon.git

# Push (rama main o master, según tu configuración)
git branch -M main
git push -u origin main
```

## Estructura de carpetas en GitHub

Home Assistant busca la estructura especial:

```
aqualia-ha-addon/
├── aqualia/              ← Esta es la carpeta del addon
│   ├── config.yaml
│   ├── Dockerfile
│   └── app/
└── README.md
```

**✓ Correcta:** el addon está en `aqualia/` (no en la raíz)

## Agregarlo a Home Assistant

### Opción 1: Crear un repositorio de addons (recomendado)

En la raíz del repo (donde ya estamos), crea `repository.yaml`:

```yaml
name: "Aqualia Addons Repository"
url: "https://github.com/tu-usuario/aqualia-ha-addon"
maintainer: "Tu Nombre <tu-email@example.com>"
```

Ahora, en Home Assistant:
- **Ajustes** → **Complementos** → **Tienda** → **⋮** → **Repositorios**
- Pega: `https://github.com/tu-usuario/aqualia-ha-addon`
- Aparecerá en la tienda automáticamente

### Opción 2: Agregar a la tienda oficial (avanzado)

1. Fork https://github.com/home-assistant/addons
2. Crea carpeta `aqualia/` en el fork
3. Copia el contenido (config.yaml, Dockerfile, etc.)
4. PR al repo oficial

## Versionado (releases)

```bash
# Crear un tag para versionado
git tag v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# Crear release en GitHub.com
# En la web: Releases → Create release → v1.0.0
# Descripción: cambios desde versión anterior
```

Actualiza `aqualia/config.yaml`:
```yaml
version: "1.0.0"  # Cambiar aquí para cada release
```

## Archivo MANIFEST.json (alternativo)

Algunos repositorios usan `MANIFEST.json` en cada addon:

```json
{
  "name": "Aqualia Water Consumption",
  "description": "Integra el consumo de agua de Aqualia en Home Assistant",
  "version": "1.0.0",
  "slug": "aqualia",
  "image": "ghcr.io/tu-usuario/aqualia-ha-addon:latest",
  "url": "https://github.com/tu-usuario/aqualia-ha-addon",
  "homeassistant": "2024.1.0"
}
```

**No es necesario** si usas `config.yaml`.

## Publicar imágenes Docker

### Opción 1: Docker Hub

```bash
# Login
docker login

# Tag y push
docker tag aqualia-ha-addon:latest tu-usuario/aqualia-ha-addon:1.0.0
docker push tu-usuario/aqualia-ha-addon:1.0.0
```

### Opción 2: GitHub Container Registry (recomendado)

```bash
# Login
echo $GHCR_TOKEN | docker login ghcr.io -u tu-usuario --password-stdin

# Tag
docker tag aqualia-ha-addon:latest ghcr.io/tu-usuario/aqualia-ha-addon:1.0.0
docker tag aqualia-ha-addon:latest ghcr.io/tu-usuario/aqualia-ha-addon:latest

# Push
docker push ghcr.io/tu-usuario/aqualia-ha-addon:1.0.0
docker push ghcr.io/tu-usuario/aqualia-ha-addon:latest
```

Luego actualiza en Dockerfile (si usas imagen pre-built):

```dockerfile
FROM ghcr.io/tu-usuario/aqualia-ha-addon:latest
```

## CI/CD con GitHub Actions

Crea `.github/workflows/build.yml`:

```yaml
name: Build & Push Docker Image

on:
  push:
    tags:
      - "v*"

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Log in to Container Registry
        uses: docker/login-action@v2
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Extract metadata
        id: meta
        uses: docker/metadata-action@v4
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=sha

      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: ./aqualia
          platforms: linux/amd64,linux/arm64,linux/arm/v7
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

Luego:
```bash
git tag v1.0.0
git push origin v1.0.0
# GitHub Actions construirá automáticamente
```

## CODEOWNERS (opcional)

Crea `.github/CODEOWNERS`:

```
* @tu-usuario
/aqualia/ @tu-usuario
```

## Licencia

Asegúrate de que el repo tiene LICENSE:

```bash
# Ejemplo: MIT
cat > LICENSE << 'EOF'
MIT License

Copyright (c) 2026 Tu Nombre

Permission is hereby granted, free of charge...
EOF

git add LICENSE
git commit -m "Add MIT license"
git push
```

## Checklist final

- ✅ Repo creado en GitHub
- ✅ Archivos pusheados
- ✅ Repository.yaml creado
- ✅ Instalable en HA
- ✅ Tag v1.0.0 creado
- ✅ README actualizado
- ✅ Licencia incluida
- ✅ .gitignore configurado

---

**Listo para compartir con la comunidad de Home Assistant!** 🎉
