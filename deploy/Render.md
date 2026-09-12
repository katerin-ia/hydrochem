# Publicar HydroChem en Render

**Gratis, sin tarjeta de crédito.** Es la opción recomendada desde que Hugging Face pasó los Docker Spaces al plan PRO.

Lo que te da el plan gratuito de Render:

- 750 horas de servicio al mes — suficiente para tenerla encendida todo el mes.
- Una dirección web propia con HTTPS: `https://hydrochem.onrender.com`.
- Se duerme tras **una semana** sin visitas (no 15 minutos), y despierta en la siguiente.
- 512 MB de memoria. Es poco, y por eso el plano de despliegue baja el cupo de visitantes simultáneos a 12.

---

## 1. Sube el proyecto a GitHub

Render despliega desde un repositorio, así que este paso es obligatorio.

**El repositorio ya está hecho**: el proyecto tiene su `git init`, su `.gitignore`
y su primer commit con los 83 archivos que hacen falta. Los datos de sesión y los
archivos subidos quedan fuera.

1. Crea una cuenta en **github.com** si no la tienes.
2. Entra en **https://github.com/new**:
   - **Repository name**: `hydrochem`
   - *Private* si no quieres que se vea
   - **NO marques** «Add a README file» — tiene que quedar vacío
   - **Create repository**
3. Copia la dirección que te muestra (`https://github.com/TU-USUARIO/hydrochem.git`).
4. **Doble clic en `deploy/Subir a GitHub.bat`**, pega esa dirección y sigue.

El `.bat` te pedirá iniciar sesión en GitHub en una ventana aparte. **Esa
contraseña la escribes tú**: no queda guardada en ningún archivo del proyecto.

> Si prefieres hacerlo a mano, desde una terminal en la carpeta `hydrochem-web`:
>
> ```bash
> git remote add origin https://github.com/TU-USUARIO/hydrochem.git
> git push -u origin main
> ```

## 2. Crea el servicio en Render

1. Entra en **render.com** → **Get Started** → **Sign in with GitHub**. No pide tarjeta.
2. En el panel: **New** → **Blueprint**.
3. Elige el repositorio `hydrochem`. Render encuentra el `render.yaml` y lo configura solo.
4. **Apply**.

La primera construcción tarda entre 4 y 8 minutos (instala pandas, numpy y matplotlib). Cuando ponga **Live**, ya está.

## 3. Compruébalo

- `https://TU-SERVICIO.onrender.com/api/health` debe devolver `{"ok": true, ...}`.
- Abre la raíz y carga el ejemplo: `data/samples/EJEMPLO-PRUEBA-LimaSur.xlsx`.

---

## Si el Blueprint no aparece

Configúralo a mano: **New** → **Web Service** → elige el repositorio, y rellena:

| Campo | Valor |
|---|---|
| Language | `Python 3` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python -m app.main` |
| Instance Type | `Free` |
| Health Check Path | `/api/health` |

Y en **Environment** añade:

```
PYTHON_VERSION      3.11
HC_WORKDIR          /tmp/hc-sessions
MPLCONFIGDIR        /tmp/matplotlib
HC_MAX_SESSIONS     12
HC_SESSION_TTL_MIN  45
HC_MAX_UPLOAD_MB    15
```

## Qué esperar del plan gratuito

| | |
|---|---|
| **Primer arranque tras dormirse** | 30–60 segundos. No se pierde nada, solo hay que esperar |
| **Memoria** | 512 MB. Con 12 sesiones y tablas de unos cientos de muestras va sobrado; con miles de filas se puede quedar corto |
| **KMZ** | Genera una imagen por muestra. Con 90 muestras son ~10 s; con 500, más de un minuto. Render corta las peticiones a los 100 s, así que para conjuntos muy grandes conviene exportar por partes |
| **Archivos subidos** | Van a `/tmp` y se borran al reiniciar el servicio. Es un espacio de trabajo, no un almacén |
| **Sin contraseñas** | Cualquiera con el enlace entra. Si los datos son sensibles, no publiques la dirección |

## Otras opciones que también funcionan

| Plataforma | Nota |
|---|---|
| **Koyeb** | Plan gratuito, escala a cero. Usa el `Dockerfile` |
| **Fly.io** | Va muy bien. Pide tarjeta aunque no cobre en el nivel gratuito |
| **Google Cloud Run** | Nivel gratuito generoso. Pide tarjeta |
| **Hugging Face Spaces** | ⚠️ **Docker requiere PRO (9 $/mes)** desde 2026. El nivel gratuito solo admite Spaces estáticos, que no pueden ejecutar Python |
| **Netlify**, **GitHub Pages**, **Vercel** (estático) | ❌ Solo sirven archivos. No ejecutan Python |

## Si lo que quieres es solo compartir resultados

Si no necesitas que otros suban sus propios datos, hay un camino mucho más simple:
un **HTML autónomo** con tu análisis dentro —Piper, Stiff, mapa y tablas, todo
interactivo— que se abre sin instalar nada y **sí** se puede publicar en Netlify,
GitHub Pages o un Space estático. Pídemelo y lo hago: es bastante menos trabajo
que esto.
