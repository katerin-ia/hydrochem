# Publicar HydroChem en Hugging Face Spaces

> ## ⚠️ Desde 2026 esto requiere plan PRO
>
> La página de precios de Hugging Face indica que el plan **PRO (9 $/mes)** es el
> que incluye «Host ZeroGPU, Gradio & Docker Spaces». El nivel gratuito solo
> admite **Spaces estáticos**, que sirven archivos pero **no ejecutan Python**, y
> por tanto no pueden correr esta aplicación.
>
> **Usa [`Render.md`](Render.md) en su lugar**: plan gratuito real, sin tarjeta,
> y el mismo proyecto sin cambios.
>
> Estas instrucciones se conservan por si tienes PRO o si Hugging Face vuelve a
> ofrecer Docker en el nivel gratuito. Comprobado el 12 de septiembre de 2026 en
> huggingface.co/pricing.

---

## 1. Crea la cuenta y el Space

1. Entra en **huggingface.co** y crea una cuenta (correo y contraseña, nada más).
2. Arriba a la derecha, tu foto → **New Space**.
3. Rellena:
   - **Space name**: `hydrochem` (o lo que quieras; será parte de la dirección).
   - **License**: la que prefieras. `mit` está bien.
   - **Select the Space SDK**: **Docker** → plantilla **Blank**.
   - **Space hardware**: *CPU basic · 2 vCPU · 16 GB*. El hardware es gratuito, pero el **SDK Docker** necesita PRO.
   - **Visibility**: *Public* si quieres compartirlo, *Private* si es solo para ti.
4. **Create Space**.

Tu dirección será `https://huggingface.co/spaces/TU-USUARIO/hydrochem`.

## 2. Sube los archivos

La forma más sencilla, sin usar git: en tu Space, pestaña **Files** → **Add file** → **Upload files**.

Arrastra **todo el contenido de la carpeta `hydrochem-web`** excepto:

- `data/sessions/` y `data/uploads/` (son datos de trabajo)
- `docs/figures/` (no hace falta)
- `.claude/`

Es decir, hacen falta: `app/`, `core/`, `tests/`, `tools/`, `data/samples/`, `Dockerfile`, `requirements.txt`, `.dockerignore` y `README.md`.

> La carpeta `app/vendor/` pesa unos 4,7 MB (Plotly y Leaflet). **Tiene que ir**: es lo que hace que la aplicación funcione sin depender de internet.

## 3. Pon la cabecera del Space en el README

Hugging Face lee la configuración del Space de las primeras líneas de `README.md`. Abre el `README.md` que acabas de subir, pincha en **Edit** y **pega esto justo al principio**, antes del `# HydroChem`:

```
---
title: HydroChem
emoji: 💧
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---
```

Guarda. El Space empezará a construirse solo.

## 4. Espera la construcción

En la pestaña **Logs** verás cómo instala las dependencias. Tarda entre 3 y 6 minutos la primera vez. Cuando ponga **Running**, tu aplicación está en línea.

Para comprobar que está viva: `https://TU-ESPACIO.hf.space/api/health` debe devolver `{"ok": true, ...}`.

---

## Lo que puedes ajustar

Pestaña **Settings** → **Variables and secrets** → **New variable**:

| Variable | Por defecto | Para qué |
|---|---|---|
| `HC_MAX_UPLOAD_MB` | `25` | Tamaño máximo de archivo que aceptas |
| `HC_MAX_SESSIONS` | `40` | Visitantes simultáneos. Cada uno guarda su tabla en memoria; en el plan gratuito no conviene subirlo mucho |
| `HC_SESSION_TTL_MIN` | `90` | Minutos sin actividad antes de olvidar una sesión y borrar sus archivos |

## Qué tiene que saber quien la use

- **No hay cuentas ni contraseñas.** Cada visitante recibe una cookie y ve solo sus propios datos, pero cualquiera con el enlace puede entrar. Si tus datos son sensibles, pon el Space en *Private*.
- **Los archivos subidos son temporales.** Se guardan en `/tmp` del contenedor, se borran al caducar la sesión, y desaparecen del todo si el Space se reinicia. No es un almacén: es un espacio de trabajo.
- **El Space se duerme** tras un tiempo sin visitas (plan gratuito) y tarda unos segundos en despertar en la siguiente. No se pierde nada, solo hay que esperar.
- **El KMZ tarda.** Genera una imagen por muestra; con 90 muestras son unos 8 segundos y con 500 puede ser más de un minuto.

## Si algo falla

| Síntoma | Qué mirar |
|---|---|
| «Build failed» | Pestaña **Logs**. Casi siempre falta un archivo o el `Dockerfile` no está en la raíz |
| Se construye pero no carga | ¿Está `app_port: 7860` en la cabecera del README? |
| La página sale sin estilos | Falta `app/static/` o `app/vendor/` |
| El KMZ da error 500 | Falta `matplotlib` en `requirements.txt`, o `MPLCONFIGDIR` no es escribible |
| «No hay datos cargados» al recargar | Normal si el Space se reinició: vuelve a cargar el archivo |

---

## Alternativas gratuitas

- **[Render](Render.md)** → la recomendada. Plan gratuito sin tarjeta, 750 h/mes, se duerme tras una semana sin visitas.
- **Koyeb** → plan gratuito, escala a cero. Usa el `Dockerfile`.
- **Fly.io** y **Google Cloud Run** → van bien, piden tarjeta aunque no cobren.

Todos leen la variable `PORT`, que la aplicación respeta.

**Netlify, GitHub Pages y los Spaces estáticos no sirven** para la aplicación: solo sirven archivos y no ejecutan Python. Sí servirían para un informe HTML autónomo (ver el final de [`Render.md`](Render.md)).
