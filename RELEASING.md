# Publicar una versión de la integración

La integración se distribuye por HACS desde
[eclyptox/aqualia-ha](https://github.com/eclyptox/aqualia-ha). HACS ofrece la actualización
cuando hay una **release** nueva en GitHub cuyo tag coincide con `version` de
`custom_components/aqualia/manifest.json`.

## CI local (no hay CI en GitHub)

Los chequeos se ejecutan en local antes de cada push:

```bash
# Una vez por clon: activa el hook pre-push versionado en .githooks/
git config core.hooksPath .githooks

# Manualmente, cuando quieras
scripts/ci.sh
```

`scripts/ci.sh` ejecuta:

1. **pytest** con cobertura (`pip install -r requirements-test.txt`).
2. **hassfest** con la imagen `ghcr.io/home-assistant/hassfest` (requiere Docker).
3. **Validación HACS** con la imagen `ghcr.io/hacs/action:main`. Revisa también el repo en GitHub
   (descripción, topics, releases), así que usa el token de `gh auth token` o `GITHUB_TOKEN`.
   `SKIP_HACS=1 scripts/ci.sh` la omite si no hay red o token.

Si algo falla, el push no sale. `git push --no-verify` lo salta (solo en emergencias).

## Pasos para una release

1. Rama nueva desde `main` y los cambios con sus tests.
2. Sube `version` en `custom_components/aqualia/manifest.json` (semver: `0.2.1` → `0.2.2`).
   Sin este cambio HACS no ofrecerá la actualización.
3. Push de la rama (pasa por la CI local) y PR contra `main`.
4. Merge del PR (squash).
5. Crea la release con el tag `v<version>` sobre `main`:

   ```bash
   git switch main && git pull
   gh release create v0.2.2 --target main --title "v0.2.2 — Resumen corto" --notes "..."
   ```

   Las notas van en español y dirigidas al usuario: qué cambia y si hace falta hacer algo
   (reconfigurar, reiniciar HA, migrar estadísticas…).
6. En Home Assistant: HACS → Aqualia → Actualizar, y reiniciar HA. Recargar la entrada no basta:
   los módulos Python ya cargados no se reimportan.

## Reglas que hassfest hace cumplir

- No listar en `requirements` del manifest paquetes que ya trae Home Assistant (`requests`,
  `cryptography`…): hassfest lo rechaza.
- Los sensores nuevos necesitan su clave en `strings.json`, `translations/en.json` y
  `translations/es.json`.
