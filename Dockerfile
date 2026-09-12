# Imagen de HydroChem. Sirve para Hugging Face Spaces, Render, Fly.io y Cloud Run.
#
# Hugging Face Spaces ejecuta el contenedor como el usuario 1000 y espera que la
# aplicacion escuche en el puerto 7860. Ambas cosas estan resueltas abajo.

FROM python:3.11-slim

# Sin bytecode ni buffer: los registros aparecen en el momento, que es lo que se
# ve en el panel del alojamiento.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Usuario sin privilegios. Spaces usa el 1000; crearlo con ese id evita
# problemas de permisos sobre los directorios de trabajo.
RUN useradd --create-home --uid 1000 hydro

WORKDIR /app

# Las dependencias en su propia capa: cambiar el codigo no fuerza a reinstalarlas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=hydro:hydro . .

# Directorios que la aplicacion escribe en marcha. HOME y MPLCONFIGDIR tienen
# que ser escribibles o matplotlib falla al generar los iconos del KMZ.
ENV HOME=/home/hydro \
    MPLCONFIGDIR=/home/hydro/.matplotlib \
    HC_WORKDIR=/tmp/hc-sessions \
    HC_SERVE_PUBLIC=1 \
    PORT=7860
RUN mkdir -p /home/hydro/.matplotlib /tmp/hc-sessions \
    && chown -R hydro:hydro /home/hydro /tmp/hc-sessions /app

USER hydro

EXPOSE 7860

# Comprobacion de vida: el alojamiento reinicia el contenedor si deja de responder.
HEALTHCHECK --interval=45s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request,os,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','7860')+'/api/health',timeout=4).status==200 else 1)"

CMD ["python", "-m", "app.main"]
