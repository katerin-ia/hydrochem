# Traspaso — HydroChem

Documento para retomar el proyecto en otra sesión. Escrito el 12 de septiembre de 2026.

**Lee esto antes de tocar nada.** Hay decisiones aquí que costaron horas de verificación y que no son evidentes leyendo el código.

---

## 1. Qué es esto

Una herramienta de análisis hidroquímico de aguas subterráneas que sustituye a un notebook de Google Colab (`hydrochemistry_lab.ipynb`). Corre en local con un doble clic y también se puede publicar en internet.

- **Ubicación**: `C:\Users\Usuario\Documents\Nuevo proyecto\hydrochem-web`
- **Estado**: funcional y completa. 303 pruebas en verde, 12 645 líneas.
- **Repositorio git**: inicializado, 3 commits, sin remoto configurado todavía.

```
b9b55c1  Declarar python-multipart, que rompia el despliegue
ecdabe0  Anadir lanzador de envio a GitHub y ajustar las instrucciones
c52ec1f  HydroChem: herramienta de analisis hidroquimico
```

## 2. El usuario

**Perfil no técnico.** Pidió explícitamente que yo tomara las decisiones técnicas y que la solución fuera **gratis**. No le expliques arquitectura salvo que pregunte; dile qué hace la herramienta y qué le falta.

Contexto: trabaja en Perú (Lima Sur, Villa El Salvador). De ahí que las zonas UTM 17S/18S/19S vayan primero en el selector y que exista una plantilla de umbrales peruanos.

## 3. Las cinco cosas que no debes romper

### 3.1 Los datos de referencia NO tienen fechas

El dataset original (90 sitios del Death Valley Regional Flow System, extraídos del libro `PiperStiff-QW-2019.v9.xlsm` de Keith Halford, USGS) **no tiene ni una celda de fecha**. Se verificó recorriendo las tres hojas del `.xlsm`.

El usuario pidió expresamente **no fabricar fechas**. El módulo `core/hydrochem/temporal.py` devuelve estructuras vacías cuando no hay fechas y la pantalla explica qué falta. Con menos de 3 campañas la aplicación muestra la evolución pero **se niega a hablar de «tendencia»**.

Para poder enseñar el módulo temporal hay dos archivos **sintéticos claramente marcados**; la app muestra un aviso permanente mientras estén cargados.

### 3.2 Los `F = 0` son «no medido», no cero real

32 de las 90 muestras traen fluoruro exactamente 0. **Decisión tomada y aplicada por defecto**, con tres pruebas que la sostienen:

- Los ceros se concentran por grupo: 100 % en *Well AD-4 corridor*, 0 % en tres grupos. La química no conoce las fronteras entre grupos; las campañas de muestreo sí.
- 23 de los 32 están en filas cuyo calcio tiene 4+ decimales — reconstruidas desde meq/L. Una reconstrucción no recupera un parámetro que no se midió.
- El mínimo realmente medido es 0,20 mg/L. Nada entre 0,01 y 0,19.

Cambia el resultado: excedencias OMS de «32 de 90» (36 %) a «32 de 58 medidas» (55 %). Es reversible con un clic desde la pantalla de validación.

### 3.3 En esta máquina `pip` no funciona

`SSL CERTIFICATE_VERIFY_FAILED` contra PyPI. **No vuelvas a intentar instalar nada.** Se sorteó así:

| Lo que faltaba | Cómo se resolvió |
|---|---|
| `pytest` | `tests/run_tests.py`, runner propio. Los tests están en estilo pytest, así que `pytest tests/` también funciona donde esté instalado |
| `pyproj` | Proyección UTM implementada en `core/hydrochem/geo/crs.py` con las series de Snyder (1987). Error de ida y vuelta: **0,25 mm** |
| `simplekml` | KML y KMZ escritos con la librería estándar en `core/hydrochem/geo/exporters/` |
| `plotly`, `leaflet` | Descargados a `app/vendor/` (4,6 MB). La app funciona sin internet |

### 3.4 Los umbrales peruanos NO están cotejados

`peru_drinking_template` en `core/hydrochem/quality/standards.py` lleva `verified=False` **a propósito**. Es una plantilla inspirada en el D.S. 031-2010-SA, sin contrastar con el texto oficial. La app lo advierte cada vez que se selecciona.

**No la presentes como oficial.** Una cifra normativa equivocada en un informe de calidad de agua tiene consecuencias. Los valores de la OMS sí van cotejados (*Guidelines for Drinking-water Quality*, 4.ª ed. 2011 + apéndice 2017).

### 3.5 Hugging Face Spaces ya no sirve gratis

Desde 2026 el SDK Docker requiere **PRO (9 $/mes)**; el nivel gratuito solo admite Spaces estáticos, que no ejecutan Python. Verificado en `huggingface.co/pricing` el 12 sept 2026 — **el usuario lo vio en pantalla antes que yo y yo le dije lo contrario de memoria**. Si surge la duda otra vez, comprueba en la web, no de memoria.

Alojamiento elegido: **Render**, plan gratuito sin tarjeta, 750 h/mes, se duerme tras una semana sin visitas.

**Netlify, GitHub Pages y Vercel no sirven**: solo archivos estáticos.

## 4. Arquitectura

```
core/hydrochem/     MOTOR CIENTÍFICO. Sin dependencias de interfaz. 23 módulos.
  constants.py          Pesos equivalentes (IUPAC2021 y PiperStiff-v9), catálogo de iones
  chemistry/            units, balance, alkalinity, facies
  geometry/             ternary, piper (2 convenciones), stiff, durov
  imputation/           5 estrategias con trazabilidad por celda
  io/                   readers, column_mapping, detection_limits
  quality/              standards (OMS + plantilla Perú)
  geo/                  crs (UTM propio) + exporters/ (kml, kmz, stiff_icons, vectors)
  validation/           rules, report
  temporal.py           Series por campaña
  pipeline.py           analyse() lo encadena todo → Dataset

app/                APLICACIÓN LOCAL
  main.py               FastAPI, 17 endpoints
  session.py            Estado por sesión con cookie
  static/               index.html, app.css, app.js (11 pantallas)
  vendor/               Plotly y Leaflet, para funcionar sin internet

tests/              303 pruebas en 16 archivos
tools/              Generadores de figuras y de archivos de ejemplo
deploy/             Render.md, HuggingFace-Spaces.md, Subir a GitHub.bat
docs/               AUDITORIA-FASE-0.md, este archivo, figures/
```

**El núcleo no importa nada de la interfaz.** Mantenlo así: es lo que permite testearlo contra el patrón de oro.

### Endpoints

```
GET  /                     GET  /api/options        GET  /api/state
POST /api/load-example     POST /api/upload         POST /api/reanalyse
POST /api/demo-campaigns   POST /api/series         POST /api/reset
GET  /api/health           GET  /api/mapping        POST /api/mapping
GET  /api/export/{kmz,kml,xlsx,csv,geojson}
```

## 5. Cómo se verifica

```bash
python tests/run_tests.py            # todo
python tests/run_tests.py piper      # filtra por nombre de archivo
```

| Archivo | Pruebas | Qué protege |
|---|---:|---|
| `test_exports.py` | 34 | KMZ, KML, GeoJSON, CSV, XLSX |
| `test_crs.py` | 28 | Proyección UTM |
| `test_facies.py` | 27 | Clasificación hidroquímica |
| `test_durov.py` | 25 | Geometría del Durov |
| `test_sessions.py` | 25 | Aislamiento entre visitantes y control de subida |
| `test_temporal.py` | 24 | Series por campaña |
| `test_standards.py` | 22 | Umbrales normativos |
| `test_piper_geometry.py` | 21 | Geometría del Piper |
| `test_readers.py` | 18 | Lectura de archivos |
| `test_imputation.py` | 16 | Estrategias de estimación |
| `test_detection_limits.py` | 14 | Valores censurados |
| `test_stiff.py` | 14 | Geometría del Stiff |
| `test_units.py` | 11 | Conversión mg/L ↔ meq/L |
| `test_balance.py` | 10 | Balance de carga |
| `test_requirements.py` | 9 | Dependencias declaradas |
| `test_alkalinity.py` | 5 | Alcalinidad |

**Las pruebas no se fían de valores recordados.** Se apoyan en testigos externos o propiedades exactas:

- meq/L **bit a bit** contra las columnas R–Z del `.xlsm` (rtol 1e-12)
- balance de carga contra su columna Q
- vértices del rombo del Piper contra su hoja oculta `CONTROL`
- las cuatro aguas puras caen exactas en los cuatro vértices del rombo
- los seis extremos del Durov caen en sus límites exactos
- el arco de meridiano de la UTM contra su **integral numérica**
- el KMZ abre como ZIP, su KML es XML válido, sin puntos en (0,0)
- control de realidad: Amargosa sale bicarbonatada (88 de 90)

## 6. Lo que se corrigió del notebook

| | Notebook | Ahora |
|---|---|---|
| Filas leídas | 89 de 90, una se perdía sin aviso (`skiprows=[1,2]`) | 90 de 90 |
| Rombo del Piper | `hw=SH/2`, `hh=hw·√3`, centro en `y=√3/2` → vértice inferior en −0,52, invadía los triángulos | `hw=0,5`, `hh=√3/2`, centro `(1+g/2, (√3/2)(1+g))` |
| Convención del Piper | Una, no estándar | Dos, seleccionables |
| Durov | Marginales sin contorno, eje Y mal rotulado, panel pH vacío | Rehecho |
| Facies | No existía | Dos esquemas |
| Flúor | Límite escrito en el código, dos veces | Cualquier parámetro contra cualquier norma |
| UTM | Zona escrita a mano; mapa y KMZ discrepaban | Selector, una sola pareja de columnas WGS84 |
| Columnas vacías | Se rellenaban con 0 y entraban en el balance | Se excluyen y se explica |
| `<0,05`, `ND` | Se perdían | Se leen como censurados |

**Hallazgo que no estaba en la auditoría inicial:** la convención del notebook no solo tiene los ápices cambiados — **su rombo no es la proyección geométrica de Piper**, es una parametrización afín. Los vértices encajan pero no se obtiene proyectando. Documentado en `geometry/piper.py`.

## 7. Estado del despliegue

**Donde lo dejamos:** el usuario subió el proyecto a GitHub e intentó desplegar en Render. **Falló** por `python-multipart` sin declarar. Ya está corregido en el commit `b9b55c1`, **pero el usuario aún no ha vuelto a desplegar**.

**Lo primero que debes preguntar:** si ya hizo `git push` y si el despliegue funcionó.

Archivos listos: `render.yaml` (blueprint), `Dockerfile`, `requirements.txt`, `deploy/Render.md`, `deploy/Subir a GitHub.bat`.

> **Lección del fallo**: `python-multipart` no aparece en ningún `import` del proyecto — lo exige FastAPI por dentro para `UploadFile`. Un repaso de imports no lo encuentra. `tests/test_requirements.py` cubre ahora esa clase de fallo.

Límites en Render (512 MB): `HC_MAX_SESSIONS=12`, `HC_SESSION_TTL_MIN=45`, `HC_MAX_UPLOAD_MB=15`.

## 8. Archivos de ejemplo

| Archivo | Qué es |
|---|---|
| `tests/fixtures/PiperStiff-QW-2019.v9.xlsm` | **Real.** El libro de Halford. Patrón de oro de las pruebas |
| `tests/fixtures/amargosa_90.csv` | **Real.** Extraído del anterior, con las columnas Q y R–Z |
| `data/samples/EJEMPLO-PRUEBA-LimaSur.xlsx` | **Inventado.** 15 estaciones × 3 campañas, UTM 18S, cabeceras en castellano, valores censurados. Para probar todo |
| `data/samples/DEMO-SINTETICO-campanas.csv` | **Inventado.** 8 campañas para el módulo temporal |

Los inventados se regeneran con `python tools/make_test_workbook.py` y `python tools/make_demo_campaigns.py`. Ambos tienen semilla fija.

## 9. Lo que falta

Por orden de valor, a mi juicio:

1. **Informe en PDF.** Es lo que más piden los usuarios de este tipo de herramienta.
2. **Guardado de proyectos.** Al cerrar la sesión se pierde lo cargado. El esquema `(station_id, sampled_at)` ya está pensado para ello.
3. **Trayectorias sobre el Piper mejoradas.** Funcionan, pero con muchas estaciones se saturan.
4. **Tendencias estadísticas** (Mann-Kendall, Sen). Necesitan 8–10 campañas: no las construyas antes de que existan datos.
5. Índices de saturación (PHREEQC), PCA, clustering, interpolación espacial, índices de riego (SAR, Wilcox, RSC).

**No empieces nada de esto sin preguntar.** El usuario puede tener otra prioridad.

## 10. Cómo trabajar aquí

- **Escribe en español**, incluidos comentarios y docstrings del código. Sin acentos en el código fuente (hay líos de codificación en esta máquina); con acentos en los textos que ve el usuario.
- **Verifica en el navegador** con `preview_start` (config `hydrochem` en `.claude/launch.json`). El panel de capturas es poco fiable: **comprueba por JavaScript** leyendo el DOM, no por captura.
- **Uvicorn no recarga solo**: tras tocar Python hay que parar y arrancar el servidor.
- **Los assets se cachean**: al tocar `app.js` o `app.css`, cambia el `?v=` en `index.html`.
- **Los heredocs de bash fallan** con contenido que lleva comillas invertidas o mezclas raras de comillas. Para archivos JS o Python largos, usa la herramienta Write o un script auxiliar en el scratchpad.
- **No cambies resultados numéricos sin pasar las pruebas del patrón de oro.** Si un valor cambia, o has arreglado un fallo o has roto algo: averigua cuál de los dos.
