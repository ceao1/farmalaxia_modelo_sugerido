# Desplegar el informe

Dos archivos HTML autocontenidos: todo el CSS, los gráficos SVG y el JavaScript van
embebidos. La única dependencia externa es la hoja de fuentes de Google, que el
navegador carga por su cuenta.

```
index.html                   informe final
analisis-exploratorio.html   análisis exploratorio (enlazado desde el informe)
```

**Los dos tienen que ir al mismo bucket y al mismo prefijo**, porque el enlace entre
ellos es relativo.

---

## Google Cloud Storage

### 1. Elegir proyecto y crear el bucket

```bash
gcloud config set project TU-PROYECTO

# el nombre es global: si está tomado, falla
gcloud storage buckets create gs://farmalaxia-informe \
  --location=us-central1 \
  --uniform-bucket-level-access
```

### 2. Subir con el tipo de contenido correcto

```bash
gcloud storage cp sitio/*.html gs://farmalaxia-informe/ \
  --content-type="text/html; charset=utf-8" \
  --cache-control="public, max-age=300"
```

> **El `charset=utf-8` no es opcional.** Sin él los acentos salen rotos —
> «recomendación» se ve como «recomendaciÃ³n». Es el error más común.

### 3. Dar acceso

**Opción A — privado, para compartir dentro de la empresa (recomendada).**
El informe contiene cifras de venta: importe anual, márgenes por marca, número de
clientes. Es lo prudente salvo que Farmalaxia haya autorizado publicarlas.

```bash
# una persona
gcloud storage buckets add-iam-policy-binding gs://farmalaxia-informe \
  --member="user:alguien@empresa.com" --role="roles/storage.objectViewer"

# todo un dominio de Google Workspace
gcloud storage buckets add-iam-policy-binding gs://farmalaxia-informe \
  --member="domain:empresa.com" --role="roles/storage.objectViewer"
```

Se abre en **`https://storage.cloud.google.com/farmalaxia-informe/index.html`**
(pide iniciar sesión con Google y respeta los permisos).

**Opción B — público.** Cualquiera con el enlace lo ve, sin sesión.

```bash
gcloud storage buckets add-iam-policy-binding gs://farmalaxia-informe \
  --member="allUsers" --role="roles/storage.objectViewer"
```

Queda en **`https://storage.googleapis.com/farmalaxia-informe/index.html`**.

### 4. Actualizarlo después

Repetir el paso 2. Con `max-age=300` los cambios se ven a los cinco minutos;
para forzarlo antes, abrir con `?v=2` al final de la URL.

---

## Sobre el dominio propio

Servir el bucket bajo `informes.suempresa.com` **no se configura solo con
`--web-main-page-suffix`**: eso solo aplica a buckets publicados con dominio propio
y requiere además un balanceador de carga HTTPS por delante. Si el informe es
interno, la Opción A evita todo ese montaje.

---

## Amazon S3

```bash
aws s3 cp sitio/ s3://TU-BUCKET/ --recursive --exclude "*" --include "*.html" \
  --content-type "text/html; charset=utf-8" \
  --cache-control "public, max-age=300"

aws s3 website s3://TU-BUCKET --index-document index.html
```

Detrás de CloudFront, invalidar tras cada actualización:

```bash
aws cloudfront create-invalidation --distribution-id TU-ID --paths "/*.html"
```

---

## Antes de publicar

- **Acentos:** que el `content-type` lleve `charset=utf-8`.
- **Los dos archivos juntos:** el informe enlaza a `analisis-exploratorio.html` por
  ruta relativa; si falta, el enlace queda roto.
- **Acceso:** el informe lleva cifras de venta de la empresa. Privado salvo
  autorización expresa.
- **Sin datos personales:** no hay nombres de clientes ni identificadores
  individuales, solo agregados.

## Regenerarlo

```bash
# para abrir los archivos localmente (enlace relativo entre ellos)
./.venv/bin/python src/13_sitio.py

# para servirlos desde un bucket con acceso autenticado
./.venv/bin/python src/13_sitio.py --base https://storage.cloud.google.com/TU-BUCKET
```

Lee de `resultados/*.json` y copia el análisis exploratorio desde `informes/`,
así que refleja siempre la última ejecución.

> **Por qué `--base`.** En `storage.cloud.google.com`, Google entrega el archivo
> desde otro host (`*.googleusercontent.com`) después de autenticar. Un enlace
> relativo se resuelve contra ese dominio y falla con 404. Con `--base` el enlace
> al análisis exploratorio queda absoluto y funciona. Para uso local, sin la
> bandera, queda relativo — que es lo correcto ahí.
