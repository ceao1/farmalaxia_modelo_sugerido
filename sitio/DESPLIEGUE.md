# Desplegar el informe

`index.html` es **un solo archivo autocontenido**: todo el CSS, los gráficos SVG y el
JavaScript del conmutador van embebidos. La única dependencia externa es la hoja de
fuentes de Google, que el navegador carga por su cuenta.

No necesita servidor de aplicaciones, ni build, ni variables de entorno.

## Amazon S3

```bash
aws s3 cp sitio/index.html s3://TU-BUCKET/index.html \
  --content-type "text/html; charset=utf-8" \
  --cache-control "public, max-age=300"

# una sola vez, para servirlo como sitio web
aws s3 website s3://TU-BUCKET --index-document index.html
```

Si el bucket está detrás de CloudFront, invalidar después de cada actualización:

```bash
aws cloudfront create-invalidation --distribution-id TU-ID --paths "/index.html"
```

## Google Cloud Storage

```bash
gcloud storage cp sitio/index.html gs://TU-BUCKET/index.html \
  --content-type="text/html; charset=utf-8" \
  --cache-control="public, max-age=300"

gcloud storage buckets update gs://TU-BUCKET --web-main-page-suffix=index.html
```

## Comprobaciones antes de publicar

- **Acentos.** El `content-type` debe llevar `charset=utf-8` o el informe se verá con
  caracteres rotos. Es el error más común al subir a S3.
- **Acceso.** El informe contiene cifras de venta de la empresa. Si el bucket es público,
  cualquiera con la URL lo ve. Conviene ponerlo tras CloudFront con acceso restringido o
  usar una URL firmada.
- **Sin datos personales.** El informe no incluye nombres de clientes ni identificadores
  individuales: solo agregados.

## Regenerarlo

```bash
./.venv/bin/python src/13_sitio.py
```

Lee de `resultados/*.json`, así que refleja siempre la última ejecución del análisis.
