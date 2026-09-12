# Auditoría técnica y plan de implementación — FASE 0

**Proyecto:** conversión del notebook `hydrochemistry_lab.ipynb` en una herramienta web de análisis hidroquímico
**Fecha:** 2026-09-11
**Estado:** auditoría cerrada. No se ha escrito ni modificado código del proyecto.

**Material auditado**

| Archivo | Tamaño | Naturaleza |
|---|---|---|
| `hydrochemistry_lab(1).ipynb` | 2.13 MB | Notebook Colab, 35 celdas (17 código / 18 markdown), 42 939 caracteres de código, con salidas ejecutadas embebidas |
| `PiperStiff-QW-2019.v9(2).zip` | 2.14 MB | Contiene 2 archivos (ver abajo) |
| └ `PiperStiff-QW-2019.v9.xlsm` | 684 KB | Libro Excel con macros VBA. Autor: **Keith Halford**. Creado 2019-01-23, modificado 2021-05-04 |
| └ `PiperStiff-EXPLAIN.v9.pdf` | 1.64 MB | Manual de usuario del libro Excel, 19 páginas |

---

## 1. Resumen ejecutivo

El notebook es un **laboratorio didáctico de hidroquímica de aguas subterráneas** que, partiendo de un Excel con concentraciones de iones mayoritarios en mg/L, hace conversión a meq/L, imputación de faltantes, balance iónico, alcalinidad, y genera cinco productos gráficos (Stiff individuales, Stiff superpuestos por grupo, Piper, Durov, análisis de flúor) más un KMZ para Google Earth y un Excel de resultados.

**La metodología científica de base es correcta y reutilizable**: los pesos equivalentes, la conversión mg/L→meq/L, el error de balance de carga (CBE) y la alcalinidad como CaCO₃ están bien implementados y se validan contra el libro Excel de referencia (las diferencias son <0,1 %, por redondeo de pesos equivalentes).

**Pero hay tres hallazgos que condicionan todo el proyecto:**

1. **El ZIP no contiene los datos que el notebook consumió.** El ZIP es una *herramienta Excel independiente* (PiperStiff, de Keith Halford, USGS) que trae su propio dataset de ejemplo. El notebook fue ejecutado con un archivo distinto (`hydrochemistry_template (1).xlsx`) que el usuario construyó trasvasando a mano la hoja `DATA` del `.xlsm` a la plantilla del notebook. No están los mismos campos en ambos lados.

2. **No existe ninguna dimensión temporal.** Cero celdas de tipo fecha en las tres hojas del `.xlsm`; ninguna columna de fecha en la plantilla del notebook; ninguna en los datos cargados. Los 90 registros son **90 sitios distintos medidos una vez**, no una serie temporal. La agrupación (7 grupos) es **hidrogeológica/espacial**, no temporal.

3. **El diagrama de Piper está geométricamente mal construido.** El rombo se dibuja con el doble de tamaño del que le corresponde y centrado demasiado bajo; el resultado es que **se solapa con los dos triángulos** y su vértice inferior cae por debajo de la línea base. Es visible en la salida ejecutada del propio notebook. La geometría correcta está implementada en el libro Excel adjunto y se especifica en la sección 5.

**Viabilidad:** alta. El cálculo científico completo son transformaciones algebraicas sobre 9–10 números por muestra; no hay nada computacionalmente costoso ni numéricamente delicado. El Piper interactivo es una transformación afín pura, ideal para portar a Plotly. El KMZ ya funciona. La parte que hay que **construir desde cero** no es el cálculo, es la **ingeniería**: validación, persistencia, API, mapa, integración cruzada y clasificación de facies (que hoy no existe en absoluto).

---

## 2. Qué hace actualmente el notebook

### 2.1 Estructura

| Celda | Tipo | Sección | Función |
|---|---|---|---|
| 0–1 | MD | — | Portada, iones cubiertos |
| 2 | Código | 1 | `!pip install`, imports, `google.colab.files` |
| 3 | MD | 2 | — |
| 4 | Código | 2 | **Genera** la plantilla `.xlsx` con openpyxl (cabeceras + fila de descripciones + fila de ejemplo) y la descarga |
| 5 | MD | 3 | — |
| 6 | Código | 3 | `files.upload()` — carga interactiva de Colab |
| 7 | MD | 4 | — |
| 8 | Código | 4 | Lector "inteligente" de Excel, validación de columnas requeridas, coerción numérica, conteo de faltantes |
| 9 | MD | 4.5 | — |
| 10 | Código | 4.5 | Detección heurística DD vs UTM y reproyección con `pyproj` → `lat_wgs84`/`lon_wgs84` |
| 11 | MD | 5 | Discusión comparativa de métodos de imputación |
| 12 | Código | 5 | Imputación por **mediana de grupo** + banderas `*_imputed` + flag de fiabilidad (>2 iones mayoritarios faltantes) |
| 13 | MD | 6 | — |
| 14 | Código | 6 | Tabla de pesos equivalentes, conversión mg/L→meq/L, `sum_cat`, `sum_an` |
| 15 | MD | 7 | — |
| 16 | Código | 7 | CBE (%) + clasificación ✅/⚠️/❌ |
| 17 | MD | 8 | — |
| 18 | Código | 8 | Alcalinidad mg/L como CaCO₃ |
| 19 | MD | 9 | — |
| 20 | Código | 9 | `draw_stiff4()` + rejilla de subplots, un Stiff por muestra → `stiff_diagrams.png` |
| 21 | MD | 10 | — |
| 22 | Código | 10 | Stiff superpuestos por grupo → `stiff_superposed.png` |
| 23 | MD | 11 | — |
| 24 | Código | 11 | `tri_xy()`, geometría de triángulos/rombo/grillas, Piper → `piper_diagram.png` |
| 25 | MD | 12 | — |
| 26 | Código | 12 | `tern_sq()`, Durov 2×2 → `durov_diagram.png` |
| 27 | MD | 13 | — |
| 28 | Código | 13 | Flúor: boxplot por grupo, F vs Ca, mapa de dispersión, informe de excedencias OMS → `fluoride_analysis.png` |
| 29 | MD | 14 | — |
| 30 | Código | 14 | KMZ: 90 PNG de Stiff + `simplekml`, carpetas por grupo, popup HTML → `hydrochemistry_sites.kmz` |
| 31 | MD | 14 *(numeración duplicada)* | — |
| 32 | Código | 14 | Tabla resumen → `hydrochemistry_results.xlsx` |
| 33 | MD | 15 | — |
| 34 | Código | 15 | Empaqueta todo en `.zip` y lo descarga |

### 2.2 Librerías

`numpy`, `pandas`, `matplotlib` (+`patches`, `gridspec`, `ticker`), `openpyxl` (+`styles`, `utils`), `pyproj.Transformer`, `simplekml`, `sklearn.impute.KNNImputer` (importado pero **solo en bloque comentado**), `scipy` (instalado pero **nunca importado ni usado**), `google.colab.files`, `os`, `warnings`, `zipfile`.

### 2.3 Constantes y variables globales relevantes

| Nombre | Celda | Contenido |
|---|---|---|
| `HEADERS`, `DESCRIPTIONS`, `EXAMPLE` | 4 | 19 columnas de la plantilla |
| `REQUIRED_COLS` | 8 | 17 columnas obligatorias (F y NO₃ son opcionales) |
| `ION_COLS_MG` | 8 | 10 iones en mg/L |
| `OPTIONAL_COLS` | 8 | `F_mgL`, `NO3_mgL` |
| `PHYS_COLS` | 8 | `pH`, `Temp_C`, `DO_mgL`, `TDS_mgL`, `Latitude`, `Longitude` |
| `UTM_ZONE = 14`, `UTM_HEMI = "north"` | 10 | **Hardcodeados** |
| `EW` | 14 | Pesos equivalentes (g/eq) |
| `CATIONS`, `ANIONS` | 14 | Listas de columnas meq |
| `MAJOR_ION_COLS` | 12 | 7 iones mayoritarios para el flag de fiabilidad |
| `WHO_F = 1.5` | 28 y 30 (`_WHO_F`) | Guía OMS de flúor, **duplicada** |
| `PALETTE`, `group_list`, `gcolors` | 20 | Paleta por grupo |
| `ROWS`, `_LEFT_LABELS`, `_RIGHT_LABELS`, `_XLIM` | 20 | Geometría Stiff |
| `SH=1.60`, `DH=√3/2`, `cx`, `hw`, `hh`, `LEVELS` | 24 | Geometría Piper |
| `df`, `df_raw`, `df_probe`, `df_imputed`, `summary` | varias | DataFrames de trabajo, reasignados en cadena |

### 2.4 Funciones

`_is_numeric`, `cbe_flag`, `draw_stiff4`, `tri_xy`, `draw_tri_grid`, `draw_diamond_grid`, `add_pct_ticks`, `tern_sq`, `_v`, `_popup`. **No hay clases.**

### 2.5 Entrada → Procesamiento → Análisis → Visualización → Exportación

```
ENTRADA        celdas 4, 6, 8          plantilla .xlsx, files.upload(), lector Excel
PROCESAMIENTO  celdas 8, 10, 12, 14    coerción de tipos, coordenadas, imputación, meq/L
ANÁLISIS       celdas 16, 18, 28       CBE, alcalinidad, excedencias OMS de F
VISUALIZACIÓN  celdas 20, 22, 24, 26, 28   Stiff ×2, Piper, Durov, F (3 paneles)
EXPORTACIÓN    celdas 30, 32, 34       KMZ, XLSX de resultados, ZIP + files.download()
```

---

## 3. Estructura de los datos

### 3.1 Lo que hay realmente en el ZIP

El ZIP **no contiene ningún CSV ni ningún dataset del notebook**. Contiene una herramienta Excel completa.

#### `PiperStiff-QW-2019.v9.xlsm` — hojas

| Hoja | Estado | Rango | Contenido |
|---|---|---|---|
| `CONTROL` | oculta | B1:CE1211 | Motor del libro: tabla de propiedades iónicas, geometría de triángulos y rombo, series de gráficos, plantillas HTML del popup KML, coordenadas precalculadas por sitio |
| `DATA` | visible | A1:AA455 | **El dataset** (filas 15–104) + configuración de cabeceras |
| `PIPER` | visible | J1:P24 | Controles de UI: grupos visibles, tamaños, escala, nombre de carpeta KMZ, orden de iones en el Stiff |

Además: `vbaProject.bin` (macros VBA), 3 gráficos, 6 controles ActiveX, 6 imágenes EMF. Nada de esto es portable a Python; es la implementación Excel del mismo análisis.

#### Hoja `DATA` — estructura real (verificada celda a celda)

Cabeceras en la **fila 14**; datos en las filas **15 a 104** = **90 registros**.

| Col | Cabecera | Tipo | Unidad | No nulos | Rango | Observación |
|---|---|---|---|---|---|---|
| A | `Longitude` | float | ° decimal WGS84 | 90/90 | −116,836 … −115,739 | Opcional según el manual |
| B | `Latitude` | float | ° decimal WGS84 | 90/90 | 36,303 … 37,059 | |
| C | `Group` | texto | — | 90/90 | 7 valores | Agrupación **hidrogeológica** |
| D | `Site` | texto | — | 90/90 | 90 únicos | Clave de facto; **sin duplicados** |
| E | `Ca²⁺` | float | mg/L | 90/90 | 1 … 74 | |
| F | `Mg²⁺` | float | mg/L | 90/90 | 0 … 40 | 1 valor = 0 |
| G | `Na⁺` | float | mg/L | 90/90 | 1,6 … 325 | |
| H | `K⁺` | float | mg/L | 90/90 | 0,4 … 27,37 | |
| I | `HCO₃⁻` | float | mg/L | 90/90 | 107 … 584 | |
| J | `CO₃⁻` | float | mg/L | 90/90 | 0 … 45 | **solo 3 muestras > 0** |
| K | `Cl⁻` | float | mg/L | 90/90 | 1,1 … 82,96 | |
| L | `SO₄²⁻` | float | mg/L | 90/90 | 9 … 235,4 | |
| M | `F⁻` | float | mg/L | 90/90 | 0 … 7,1 | **32 de 90 valen exactamente 0** → ver §12 R3 |
| N, O | *(vacías)* | — | — | 0/90 | — | Columnas de iones libres, sin usar |
| P | `TDS, mg/L` | float | mg/L | 90/90 | 194 … 1121 | |
| Q | `Charge balance` | float | fracción | 90/90 | −0,0348 … +0,0457 | **Calculado**, no medido. Ninguno supera ±5 %; 20 superan ±2 % |
| R–Z | `Ca²⁺ … F⁻` | float | meq/L | 90/90 | — | **Derivados** por fórmula Excel |

**Grupos (columna C):**

| Grupo | n |
|---|---:|
| Central Amargosa Desert | 38 |
| Western Amargosa Desert | 14 |
| Ash Meadows discharge area | 13 |
| Yucca Mtn–Jackass Flats | 12 |
| Carbonate in Ash Meadows | 8 |
| Furnace Creek | 3 |
| Well AD-4 corridor | 2 |

**Contexto geográfico:** Death Valley Regional Flow System (Nevada / California, EE. UU.). Extensión ≈ 1,10° lon × 0,76° lat ≈ 98 × 84 km.

**NO existen en el `.xlsm`:** fecha, hora, campaña, pH, temperatura, oxígeno disuelto, NO₃, profundidad, cota, tipo de punto (pozo/manantial), código de estación numérico, sistema de coordenadas declarado, límites de detección, laboratorio, método analítico.

### 3.2 Lo que el notebook consumió realmente

La salida ejecutada de la celda 6 dice: `Saving hydrochemistry_template.xlsx to hydrochemistry_template (1).xlsx`. Es decir, **el usuario descargó la plantilla del notebook, pegó a mano los datos de la hoja `DATA`, y la volvió a subir**. Resultado registrado en la celda 8:

- `✅ Loaded 89 samples` — **89, no 90** (ver §12 R1)
- Los mismos 7 grupos
- `Sample_ID` de 2 a 90 (numéricos, asignados a mano)
- `Sample_Name` = el `Site` del Excel
- `Latitude`/`Longitude` = los del Excel, en grados decimales
- `TDS_mgL` presente
- **`pH`, `Temp_C`, `DO_mgL`: 100 % vacíos** (no existen en el origen)
- **`NO3_mgL`: 89/89 nulos** (no existe en el origen)
- 0 faltantes en los 9 iones restantes

### 3.3 Esquema de la plantilla del notebook (celda 4)

19 columnas: `Group`, `Sample_ID`, `Sample_Name`, `Latitude`, `Longitude`, `pH`, `Temp_C`, `DO_mgL`, `TDS_mgL`, `Ca_mgL`, `Mg_mgL`, `Na_mgL`, `K_mgL`, `HCO3_mgL`, `CO3_mgL`, `SO4_mgL`, `Cl_mgL`, `F_mgL`, `NO3_mgL`.
Formato: fila 1 = cabeceras, fila 2 = descripciones, fila 3 = ejemplo, fila 4+ = datos.
**Ninguna columna de fecha.**

### 3.4 Correspondencia entre ambos esquemas

| Notebook | `.xlsm` `DATA` | Estado |
|---|---|---|
| `Group` | C `Group` | ✅ directo |
| `Sample_Name` | D `Site` | ✅ directo |
| `Sample_ID` | — | ⚠️ inventado a mano |
| `Latitude` / `Longitude` | B / A | ✅ directo (ojo: orden invertido) |
| `TDS_mgL` | P | ✅ directo |
| `Ca…Cl_mgL`, `F_mgL` | E–M | ✅ directo |
| `pH`, `Temp_C`, `DO_mgL`, `NO3_mgL` | — | ❌ **no existen en el origen** |
| — | Q `Charge balance`, R–Z meq/L | ℹ️ el notebook los recalcula |

---

## 4. Flujo actual del procesamiento

```
   [Hoja DATA del .xlsm]   ← 90 sitios, mg/L, lon/lat, sin fecha, sin pH
              │
              │  (trasvase MANUAL a la plantilla del notebook — paso no automatizado)
              ▼
   [hydrochemistry_template.xlsx]
              │
              ▼
   CARGA  · celdas 6 + 8
   files.upload() → pd.read_excel(skiprows=[1,2]) → validación de 17 columnas
   → to_numeric(errors='coerce') → conteo de faltantes
   ⚠ PIERDE LA PRIMERA FILA DE DATOS (90 → 89)
              │
              ▼
   COORDENADAS  · celda 10
   heurística DD vs UTM → pyproj EPSG:326xx/327xx → EPSG:4326
   → columnas lat_wgs84 / lon_wgs84
              │
              ▼
   IMPUTACIÓN  · celda 12
   mediana de grupo → mediana global → 0.0
   banderas Ca_imputed … NO3_imputed
   flag "reliability" si >2 iones mayoritarios faltan
   ⚠ NO₃ (100 % vacío) acaba imputado a 0 y contabilizado como anión
   ⚠ pH / Temp / DO NO se imputan nunca
              │
              ▼
   CONVERSIÓN  · celda 14
   meq/L = mg/L ÷ EW   →  10 columnas *_meq, sum_cat, sum_an
              │
              ├──────────────┬──────────────┐
              ▼              ▼              ▼
   CBE · celda 16     ALCALINIDAD      (nada más)
   (Σcat−Σan)/        celda 18
   (Σcat+Σan)×100     (HCO₃+CO₃)meq
   → flag ✅/⚠️/❌      × 50,04
              │
              ▼
   VISUALIZACIÓN
   ├─ celda 20  Stiff por muestra (89 subplots)      → stiff_diagrams.png
   ├─ celda 22  Stiff superpuestos por grupo (7)     → stiff_superposed.png
   ├─ celda 24  PIPER (2 ternarios + rombo)          → piper_diagram.png   ⚠ geometría rota
   ├─ celda 26  Durov (2×2)                          → durov_diagram.png   ⚠ panel pH vacío
   └─ celda 28  Flúor (box + F/Ca + mapa)            → fluoride_analysis.png ⚠ usa coords crudas
              │
              ▼
   EXPORTACIÓN
   ├─ celda 30  89 PNG de Stiff + simplekml          → hydrochemistry_sites.kmz
   ├─ celda 32  tabla de 30 columnas                 → hydrochemistry_results.xlsx
   └─ celda 34  zipfile + files.download()           → hydrochemistry_outputs.zip
```

### 4.1 Etapa por etapa

| Etapa | Qué hace | Datos que usa | Resultado | Código | Reutilizable |
|---|---|---|---|---|---|
| Plantilla | Construye un `.xlsx` con estilos | Constantes | Archivo descargable | c.4 | **C** — sustituir por endpoint |
| Carga | Detecta formato plantilla/plano y lee | Archivo del usuario | `df_raw` | c.8 | **B** — corregir `skiprows` |
| Validación | Comprueba 17 columnas, coerce a numérico | `df_raw` | `df`, conteo de nulos | c.8 | **B** — devolver objeto de validación, no `print` |
| Coordenadas | Heurística DD/UTM + reproyección | `Latitude`,`Longitude` | `lat_wgs84`,`lon_wgs84` | c.10 | **A/B** — quitar globals y `print` |
| Imputación | Mediana de grupo con doble fallback | 10 iones + `Group` | `df_imputed`, 10 banderas | c.12 | **B** — vectorizar, no imputar columnas 100 % vacías |
| Conversión | mg/L ÷ EW | 10 iones | 10 col. `*_meq`, sumas | c.14 | **A** |
| CBE | Balance de carga | `sum_cat`,`sum_an` | `CBE_pct`, `CBE_flag` | c.16 | **A** |
| Alcalinidad | (HCO₃+CO₃) × 50,04 | 2 col. meq | `Alkalinity_mgCaCO3` | c.18 | **A** |
| Stiff | Polígono de 4 filas | 7 agregados meq | PNG | c.20 | **B** — lógica sí, render no |
| Stiff grupo | Superposición | ídem + `Group` | PNG | c.22 | **B** — código duplicado de c.20 |
| Piper | 2 ternarios + rombo | 6 agregados meq | PNG | c.24 | **B** — corregir rombo |
| Durov | 2×2 paneles | 6 meq + pH + TDS | PNG | c.26 | **C** — rehacer |
| Flúor | 3 paneles + informe | `F_mgL`,`Ca_mgL`, coords | PNG + texto | c.28 | **B/C** |
| KMZ | 89 PNG + simplekml | Todo `df` | KMZ | c.30 | **B** — `_popup` es **A** |
| Resumen | Selección de 30 columnas | `df` | XLSX | c.32 | **B** |
| Descarga | zip + `files.download` | Archivos | ZIP | c.34 | **C** |

---

## 5. Análisis del diagrama de Piper

### 5.1 Variables y unidades

Trabaja **íntegramente en meq/L**. Entrada, 6 agregados por muestra:

| Vértice | Triángulo catiónico | Triángulo aniónico |
|---|---|---|
| Inferior izquierdo | `Ca_meq` | `HCO3_meq + CO3_meq` |
| Inferior derecho | `Mg_meq` | `SO4_meq` |
| Ápice superior | `Na_meq + K_meq` | `Cl_meq + F_meq + NO3_meq` |

La inclusión de F⁻ y NO₃⁻ en el vértice del cloruro es una **decisión deliberada y documentada** del autor del notebook (celda 23), no un error. El libro Excel de referencia hace lo mismo con F⁻ (`An_Bottom = Cl + F`) pero no incluye NO₃.

### 5.2 Cálculo de posiciones

```python
def tri_xy(a, b, c):
    tot = a + b + c;  tot = np.where(tot == 0, 1, tot)
    a, b, c = a/tot, b/tot, c/tot
    return 0.5*(2*b + c), (np.sqrt(3)/2)*c
```

Normalización a fracción dentro de la propia función. Mapeo: A→(0,0), B→(1,0), C→(0,5, √3/2). **Verificado correcto**, igual que `draw_tri_grid` (las tres familias de isolíneas se comprobaron analíticamente y son exactas).

Proyección al rombo:

```python
nak_pct = nak / cat_tot ;  clf_pct = clf / an_tot
dx = 0.5 + hw*(nak_pct + clf_pct)
dy = DH  + hh*(nak_pct - clf_pct)
```

Es una aplicación afín correcta **para la geometría que el notebook dibuja**: (0,0)→vértice izquierdo, (1,1)→derecho, (1,0)→superior, (0,1)→inferior.

### 5.3 ⛔ Defecto geométrico confirmado

```python
SH = 1.60                  # separación entre triángulos
DH = np.sqrt(3)/2          # 0,8660
cx = 0.5 + SH/2            # 1,30
hw = SH/2                  # 0,80   ← incorrecto
hh = hw*np.sqrt(3)         # 1,3856 ← incorrecto
```

Con esos valores el vértice inferior del rombo cae en **y = 0,866 − 1,386 = −0,52**, es decir **por debajo de la base de los triángulos**, y los vértices izquierdo y derecho coinciden con los ápices de los triángulos. **El rombo invade ambos triángulos.** Se comprueba a simple vista en la salida `piper_diagram.png` embebida en el notebook: las etiquetas `Na⁺+K⁺` y `Cl⁻+F⁻+NO₃⁻` quedan dentro del rombo y las aristas se cruzan con los triángulos.

**Geometría correcta** (triángulos de lado 1, hueco `g = SH − 1`):

| Parámetro | Fórmula | Valor con `SH = 1,6` (`g = 0,6`) | Valor actual |
|---|---|---|---|
| Semianchura del rombo | `hw = 0,5` | 0,500 | 0,800 ❌ |
| Semialtura | `hh = √3/2` | 0,866 | 1,386 ❌ |
| Centro X | `cx = 1 + g/2` | 1,300 | 1,300 ✅ |
| Centro Y | `cy = (√3/2)·(1 + g)` | 1,386 | 0,866 ❌ |
| Vértice inferior | `(cx, (√3/2)·g)` | (1,300 · 0,520) | (1,300 · −0,520) ❌ |

Esta geometría **está verificada contra el propio libro Excel adjunto**: la hoja `CONTROL` define el rombo con vértices (1,15 · 0,2598), (0,65 · 1,1258), (1,15 · 1,9919), (1,65 · 1,1258) y `Offset = 0,3`, que satisfacen exactamente las fórmulas anteriores con `g = 0,3`.

Con el rombo corregido, la proyección pasa a ser:

```python
dx = cx + hw*((nak_pct + clf_pct) - 1)
dy = cy + hh*( nak_pct - clf_pct)
```

### 5.4 Orientación: no es la convención clásica

La convención de libro de texto sitúa **Mg²⁺** en el ápice del triángulo catiónico y **SO₄²⁻** en el ápice del aniónico. El notebook sitúa **Na⁺+K⁺** y **Cl⁻+F⁻+NO₃⁻**. El libro Excel usa una tercera variante (`Cat_Side = Mg`, `An_Side = SO₄`, con Na+K y HCO₃+CO₃ marcados como `DIAMOND`).

No es un error —es internamente coherente y las etiquetas dibujadas concuerdan con lo graficado— **pero tiene una consecuencia práctica seria**: las plantillas clásicas de clasificación de facies hidroquímicas (los cuadrantes y subcampos del rombo de Piper) **no se pueden superponer directamente** sobre este gráfico. Antes de implementar clasificación hay que fijar la convención. **Recomendación: adoptar la convención clásica** (Mg y SO₄ en los ápices) y hacer la orientación configurable, para que la clasificación de facies sea estándar y comparable con la literatura.

### 5.5 Clasificación

**No existe.** El notebook no clasifica ninguna muestra. No hay facies, ni tipo de agua, ni campos del rombo. Los "grupos" son etiquetas de entrada, no resultado de análisis. Esto es funcionalidad **a desarrollar**, no a portar.

### 5.6 Identificación de grupos y estética

Bucle `for grp in group_list` con color `gcolors[grp]` de `plt.cm.tab10`. Círculos en los triángulos, rombos (`marker='D'`) en el rombo. Sin etiquetas por muestra, sin tooltips, sin resaltado.

### 5.7 Portabilidad a web — muy alta

| Aspecto | Valoración |
|---|---|
| Coste de cálculo | Despreciable: 6 sumas + 2 divisiones + 4 multiplicaciones por muestra |
| Estado | Sin estado; función pura `(6 meq) → (x_cat, y_cat, x_an, y_an, x_diam, y_diam)` |
| Fondo del gráfico | Estático: 3 polígonos + ~24 líneas de rejilla + ~30 etiquetas. Se calcula una vez y se sirve como *shapes* de Plotly o SVG |
| Datos | Un array de N puntos ×3 series. `Scattergl` de Plotly aguanta decenas de miles sin problema |
| Interactividad | Nativa: `hovertemplate`, `customdata`, evento `plotly_click`/`plotly_selected` para la selección cruzada con el mapa |
| Riesgo | Bajo. Único trabajo real: corregir la geometría (§5.3) y decidir la convención (§5.4) |

**Información a mostrar al seleccionar una muestra** (todo disponible o derivable hoy):
sitio, grupo, coordenadas, %Ca / %Mg / %Na+K, %HCO₃+CO₃ / %SO₄ / %Cl+F+NO₃, concentraciones en mg/L y meq/L de los 10 iones, TDS, CBE con su semáforo, alcalinidad, facies hidroquímica *(a desarrollar)*, banderas de imputación, estado OMS del flúor, miniatura del Stiff y —cuando existan fechas— la fecha de muestreo y el enlace a la serie temporal de esa estación.

---

## 6. Análisis de la dimensión temporal

### 6.1 Qué existe hoy — respuesta directa: **nada**

Verificación exhaustiva realizada:

- Recorrido de las **tres hojas completas** del `.xlsm` buscando celdas de tipo fecha/datetime → **0 coincidencias**.
- Cabeceras de `DATA` (fila 14) → ninguna columna temporal. Las columnas N y O están vacías.
- Plantilla del notebook (celda 4, 19 columnas) → ninguna columna temporal.
- Salida ejecutada del notebook → ninguna referencia a fechas.
- El manual PDF menciona fechas **una sola vez**, en el changelog de la v5, y para advertir de lo contrario: *si un usuario usa fechas como nombre de sitio, aparecerán como días decimales desde 1/1/1900*. Es decir, el propio autor documenta que el libro **no tiene concepto de fecha**.

### 6.2 Clasificación observado / derivado / estimado

| Categoría | Campos | n | Nota |
|---|---|---|---|
| **Observados** (existen realmente) | `Longitude`, `Latitude`, `Group`, `Site`, Ca, Mg, Na, K, HCO₃, CO₃, Cl, SO₄, F, TDS | 90 × 14 | TDS puede ser medido o calculado; el manual dice que el programa suma iones para TDS, así que su procedencia es **ambigua** |
| **Derivados** (calculados de los observados) | 10 × `*_meq`, `sum_cat`, `sum_an`, `CBE_pct`, `CBE_flag`, `Alkalinity_mgCaCO3`, `lat_wgs84`, `lon_wgs84`, %ternarios, coordenadas de gráfico | — | Reproducibles y trazables |
| **Estimados / imputados** | 89 valores de `NO3_mgL` puestos a **0,0** por el fallback de la imputación; los 32 `F = 0` que probablemente son "no medido" codificado como 0 | 89 + 32 | Marcados con `NO3_imputed = True`; los F=0 **no están marcados** |
| **Temporales** | — | **0** | **No existen. No deben inventarse.** |

> **Regla de diseño no negociable:** la aplicación no debe generar, interpolar ni suponer fechas. Un dataset sin fecha es un dataset de **una campaña sin fechar**, y así debe presentarse.

### 6.3 Cómo preparar la aplicación para datos multi-fecha

El objetivo no es simular una serie temporal, sino que **el día que lleguen 2, 5 o 40 campañas no haya que reescribir el modelo de datos**. La clave es separar desde el primer commit el *punto de muestreo* de la *muestra*:

```
stations                       samples                        results
─────────                      ─────────                      ─────────
station_id  (PK)        1 ─< n sample_id     (PK)      1 ─ 1  sample_id (PK,FK)
code                          station_id    (FK)             ca_meq … no3_meq
name                          sampled_at    (nullable)       sum_cat, sum_an
group                         campaign_id   (nullable)       cbe_pct, cbe_flag
lon, lat, crs                 ca_mgl … no3_mgl                alkalinity
site_type                     ph, temp_c, do_mgl, tds        facies_code
elevation                     lab, method                    x_cat,y_cat,x_an,y_an,x_dia,y_dia
                              imputation_flags (JSON)
                              UNIQUE (station_id, sampled_at)
```

Consecuencias concretas:

- La clave natural de una muestra es **(estación, fecha)**, no el nombre del sitio. Hoy `sampled_at` es `NULL` para las 90 muestras y la restricción `UNIQUE` sigue siendo válida (una sola muestra sin fecha por estación).
- Toda consulta de análisis recibe un **filtro temporal opcional**. Con datos actuales devuelve todo; con datos futuros filtra sin tocar nada más.
- La UI incorpora desde el MVP un selector de campaña/fecha que, cuando no hay fechas, se muestra **deshabilitado con la leyenda "campaña única — sin fecha registrada"**. Así el usuario ve que la capacidad existe y por qué está inactiva, en lugar de descubrir más tarde que no está.
- La plantilla de carga incluye ya las columnas `Sampled_Date` y `Campaign` como **opcionales**, documentadas en la fila de descripciones. Coste cero hoy, cero fricción mañana.

### 6.4 Análisis temporales — evaluación de viabilidad (sin implementar)

| Análisis | Viabilidad técnica | Requisito mínimo de datos | Prioridad |
|---|---|---|---|
| Piper filtrado por fecha concreta | Trivial — es un `WHERE` sobre `samples` | ≥1 fecha | V2 |
| Piper de un periodo (rango) | Trivial | ≥2 fechas | V2 |
| **Trayectoria de una estación en el Piper** (unir sus puntos por orden cronológico) | Fácil y de **alto valor científico**: muestra la evolución de la facies | ≥3 campañas en la misma estación | V2 |
| Serie temporal de un parámetro por estación | Fácil | ≥3 campañas | V2 |
| Comparación entre estaciones en la misma fecha | Fácil | ≥2 estaciones con fecha común | V2 |
| Boxplot por campaña | Fácil | ≥2 campañas | V2 |
| **Cambio de clasificación hidroquímica entre campañas** (matriz de transición de facies) | Media — depende de tener clasificador de facies fiable | ≥2 campañas + clasificador | V3 |
| Tendencias estadísticas (Mann-Kendall, pendiente de Sen) | Media — la implementación es estándar, el problema es la potencia estadística | **≥8–10 campañas** por estación | V3 |
| Descomposición estacional | Baja con datos de agua subterránea típicos | ≥24 campañas regulares | Fuera de alcance |
| Interpolación temporal / relleno de huecos | **Desaconsejada** | — | **No hacer** |

**Conclusión de la sección:** con los datos actuales **ningún** análisis temporal es ejecutable. Lo correcto es dejar la puerta abierta con el esquema y la UI, y no construir los módulos temporales hasta que exista una segunda campaña real.

---

## 7. Análisis de la componente espacial

### 7.1 Qué información geográfica existe

| Elemento | Existe | Detalle |
|---|---|---|
| Latitud | ✅ | Grados decimales, 36,303 – 37,059 |
| Longitud | ✅ | Grados decimales, −116,836 – −115,739 |
| Sistema de coordenadas | ⚠️ **Implícito** | Es claramente WGS84 geográfico por el rango y la región, pero **no está declarado** en ninguna parte |
| UTM | ❌ | No hay. El notebook *soporta* UTM, pero estos datos no lo usan |
| Código de estación | ⚠️ | Solo el nombre textual (`Site`), 90 únicos. El propio manual advierte de que el libro desduplica nombres repetidos añadiendo un sufijo → **no es una clave fiable a largo plazo** |
| Agrupación espacial | ✅ | `Group`: 7 unidades hidrogeológicas, de 2 a 38 sitios |
| Elevación / profundidad | ❌ | No hay |
| Tipo de punto (pozo / manantial / piezómetro) | ❌ | Inferible del nombre ("Spring", "Well", "WW"), pero no es un campo |
| Geometrías (acuífero, cuenca, fallas) | ❌ | No hay |

### 7.2 Manejo actual de coordenadas en el notebook

1. Heurística de detección (celda 10): marca UTM si `|lat| > 90`, o `|lon| > 180`, o (>50 % de longitudes entre 100 000 y 900 000 **y** latitud máxima > 1000).
2. Si es UTM: `EPSG:326{zona}` (norte) o `EPSG:327{zona}` (sur) → `EPSG:4326`, con `UTM_ZONE` y `UTM_HEMI` **escritos a mano en el código**.
3. Si es DD: copia directa a `lat_wgs84` / `lon_wgs84`.
4. **Inconsistencia:** el mapa de flúor (celda 28) usa `df["Longitude"]` / `df["Latitude"]` **crudos**, mientras que el KMZ (celda 30) usa `lon_wgs84` / `lat_wgs84`. Con entrada UTM, el mapa saldría en metros y el KMZ en grados.

### 7.3 Mapa interactivo — viabilidad

Alta y sin obstáculos. 90 puntos es un volumen trivial; incluso 100 000 muestras se manejan con *clustering* o teselas vectoriales.

Capacidades que la herramienta debería ofrecer:

- Puntos de muestreo coloreados por **grupo**, por **facies hidroquímica**, por **parámetro continuo** (TDS, F, Cl…) o por **estado del CBE**.
- Tamaño de símbolo proporcional a un parámetro (p. ej. TDS).
- **Icono de Stiff** dibujado como SVG en la posición del punto (equivalente web de lo que hace el KMZ) — es el rasgo distintivo de la herramienta original y merece conservarse.
- Popup con la ficha completa de la muestra + miniatura del Stiff + Piper en miniatura.
- Filtros vinculados: grupo, rango de parámetro, CBE aceptable, excedencia OMS, campaña/fecha.
- Capas base intercambiables (satélite / topográfica / clara) y control de opacidad.
- Herramienta de selección por rectángulo/polígono que alimente la selección cruzada (§8).
- Leyenda, escala, coordenadas del cursor y exportación de la vista a PNG.

### 7.4 Exportación geoespacial

| Formato | Viabilidad | Notas |
|---|---|---|
| **CSV** | Trivial | Tabla plana con lon/lat y todos los derivados |
| **GeoJSON** | Trivial | Sin dependencias; `json.dumps` de un `FeatureCollection`. Es el formato natural para alimentar el propio frontend |
| **KML** | Fácil | `simplekml` ya está en uso |
| **KMZ con Stiff embebidos** | ✅ **Ya funciona** | El notebook produce un KMZ con 89 placemarks, carpetas por grupo, estilos de color e imágenes PNG del Stiff en `files/`. El popup HTML (`_popup`) es de buena calidad y **reutilizable casi tal cual** |
| Shapefile | Posible | Requiere `fiona`/`geopandas`; limitación de 10 caracteres en nombres de campo. **No recomendado** salvo petición expresa |
| GeoPackage | Posible | Mejor alternativa que shapefile si se pide un formato SIG "de verdad" |

**Puntos de atención para el KMZ compatible con Google Earth** (todos verificados en el código actual):

- ✅ El orden de coordenadas es `(lon, lat)` — correcto para KML.
- ✅ `kml.addfile()` deposita las imágenes en `files/` y el `<img src="files/...">` del popup coincide.
- ✅ El HTML del popup va envuelto en `<![CDATA[ ]]>`.
- ⚠️ **Rendimiento:** genera **una figura matplotlib por muestra** (90 figuras → decenas de segundos). En una aplicación web esto **debe** ser una tarea asíncrona con barra de progreso, o sustituirse por SVG generado directamente (mucho más rápido y de mejor calidad).
- ⚠️ La carpeta "Legend" coloca placemarks ficticios en **(0, 0)** — en el Golfo de Guinea. Hay que sustituirla por un `ScreenOverlay` o eliminarla.
- ⚠️ Los separadores decimales deben forzarse a punto independientemente del *locale* (el manual documenta este bug corregido en la v7 del libro Excel; `simplekml` lo hace bien, pero conviene tenerlo presente).
- ⚠️ Google Earth **Web** no admite todo lo que admite Google Earth Pro. El objetivo declarado del usuario es Google Earth, y Pro es el destino seguro.

---

## 8. Integración mapa ↔ Piper

### 8.1 ¿Lo permiten los datos actuales? Sí, sin condiciones

Cada registro tiene simultáneamente: un identificador único (`Site`), una posición (lon/lat) y una composición química completa. Eso es todo lo que hace falta. El único requisito estructural es sustituir el nombre del sitio por un **identificador estable generado por el sistema**, porque el nombre es texto libre susceptible de duplicarse.

### 8.2 Estructura de datos necesaria

Un único objeto por muestra, calculado una vez en el backend y compartido por todas las vistas:

```jsonc
{
  "sample_id": "s_0042",           // clave estable, generada
  "station_id": "st_0042",
  "site": "Devils Hole",
  "group": "Ash Meadows discharge area",
  "sampled_at": null,              // hoy null; mañana ISO-8601
  "geo": { "lon": -116.291, "lat": 36.425, "crs": "EPSG:4326" },
  "mgl":  { "Ca": 50.25, "Mg": 20.75, ... },
  "meq":  { "Ca": 2.508, "Mg": 1.707, ... },
  "derived": { "sum_cat": 7.366, "sum_an": 7.396,
               "cbe_pct": -0.205, "cbe_flag": "ok",
               "alkalinity": 245.9, "tds": 460 },
  "piper": { "cat": [x,y], "an": [x,y], "diamond": [x,y],
             "pct_cat": {"Ca":0.34,"Mg":0.23,"NaK":0.43},
             "pct_an":  {"HCO3CO3":0.61,"SO4":0.23,"ClFNO3":0.16} },
  "stiff": { "na_k": 3.13, "ca": 2.51, "mg": 1.71,
             "cl": 0.67, "so4": 1.72, "hco3_co3": 4.92, "f_no3": 0.08 },
  "facies": "Ca-Mg-HCO3",          // a desarrollar
  "flags":  { "imputed": ["NO3"], "who_f_exceeded": true, "reliable": true }
}
```

Con esto, mapa, Piper, Stiff, Durov y tabla **leen exactamente el mismo array**, y la selección es simplemente un `Set<sample_id>` en el estado global de la aplicación.

### 8.3 Flujos de interacción

```
Seleccionar punto en el MAPA
        ↓  actualiza selection = {sample_id}
        ├─→ PIPER: resalta los 3 marcadores de esa muestra (opacidad del resto al 25 %)
        ├─→ STIFF: dibuja el polígono de esa muestra
        ├─→ PANEL: ficha completa (mg/L, meq/L, CBE, alcalinidad, facies, banderas)
        ├─→ TABLA: hace scroll a la fila y la marca
        └─→ TEMPORAL: si la estación tiene >1 muestra, traza su serie y su
                      trayectoria en el Piper   [inactivo con los datos actuales]

Seleccionar punto (o lazo) en el PIPER
        ↓  mismo estado compartido
        ├─→ MAPA: hace zoom/flyTo y resalta los puntos correspondientes
        ├─→ PANEL y TABLA igual que arriba
        └─→ permite selección múltiple por región del rombo → "todas las aguas
            cloruradas-sódicas de esta zona", que es el caso de uso más potente

Filtrar en la TABLA o en los controles
        └─→ mapa, Piper, Stiff y Durov se refiltran de forma coordinada
```

### 8.4 Implementación

Un **único estado compartido** (Zustand o Context de React) con `{ data, filters, selection, hover }`. Plotly emite `plotly_click`, `plotly_selected` y `plotly_hover`; MapLibre emite `click` y `mousemove` sobre la capa. Ambos escriben en el mismo estado y ambos se re-renderizan desde él. Para el resaltado sin repintar el gráfico entero se usa `Plotly.restyle` sobre `marker.opacity` y `marker.line.width`, que es una operación barata.

**Es aquí donde se decide la arquitectura del frontend.** Este patrón es natural en React y muy incómodo en Streamlit, porque Streamlit re-ejecuta el script completo en cada interacción y pierde el estado de cámara del mapa y del gráfico.

---

## 9. Funcionalidades propuestas (priorizadas)

### MVP — herramienta mínima útil

| # | Funcionalidad | Justificación |
|---|---|---|
| M1 | Carga de Excel/CSV con **mapeo configurable de columnas** | El caso real ya obligó a un trasvase manual. Sin esto, el problema persiste |
| M2 | Descarga de plantilla (con `Sampled_Date` y `Campaign` opcionales) | Sustituye la celda 4 |
| M3 | Informe de validación: columnas, tipos, rangos, faltantes, duplicados, CBE, límites de detección | Hoy es un `print` con emojis; debe ser un objeto estructurado y una pantalla |
| M4 | Conversión mg/L → meq/L con tabla de pesos equivalentes **visible y editable** | Núcleo, ya resuelto |
| M5 | CBE y alcalinidad con semáforo | Núcleo, ya resuelto |
| M6 | Imputación configurable (ninguna / mediana de grupo / KNN) con banderas y **negativa a imputar columnas 100 % vacías** | Corrige el fallo de NO₃ |
| M7 | **Piper interactivo con geometría corregida**, color por grupo, hover, selección | Producto estrella |
| M8 | Tabla de resultados filtrable y ordenable | |
| M9 | **Mapa interactivo** con puntos, popup y color por atributo | |
| M10 | Exportación CSV / XLSX / GeoJSON / **KMZ con Stiff** | El KMZ es el diferenciador frente a cualquier dashboard genérico |

### V2 — herramienta profesional

| # | Funcionalidad |
|---|---|
| V2.1 | **Clasificación de facies hidroquímicas** (Piper clásico; opcionalmente Stuyfzand o Custodio) con color y filtro por facies |
| V2.2 | Stiff interactivos: individuales, superpuestos por grupo, e **icono Stiff sobre el mapa** |
| V2.3 | **Selección cruzada completa mapa ↔ Piper ↔ Stiff ↔ tabla** |
| V2.4 | Durov correcto (marginales con contorno, ejes bien etiquetados, pH y TDS reales) |
| V2.5 | Módulo de parámetros normativos configurable (OMS, y normativa local — en Perú, D.S. 004-2017-MINAM / DIGESA) sustituyendo el `WHO_F` fijo |
| V2.6 | Relaciones iónicas y gráficos de Gibbs, Na/Cl, Ca/Mg, (Ca+Mg)/(HCO₃+SO₄) |
| V2.7 | **Análisis temporal** (activo solo si hay ≥2 fechas): Piper por campaña, trayectorias, series por parámetro |
| V2.8 | Reporte HTML/PDF exportable con todos los gráficos y tablas |
| V2.9 | Persistencia de proyectos: guardar/cargar/versionar un conjunto de datos |

### V3 — avanzado

| # | Funcionalidad |
|---|---|
| V3.1 | Tendencias (Mann-Kendall, Sen) y matriz de transición de facies |
| V3.2 | Índices de saturación (integración con `phreeqpython`/PHREEQC) |
| V3.3 | Estadística multivariante: PCA, clustering jerárquico, dendrograma sobre composición |
| V3.4 | Interpolación espacial (IDW / kriging) y mapas de isolíneas de un parámetro |
| V3.5 | Índices de calidad para riego (SAR, Wilcox, RSC) y para consumo (WQI) |
| V3.6 | Multiusuario, control de acceso, auditoría de cambios |
| V3.7 | API pública documentada para integrar con otros sistemas |

---

## 10. Propuesta de interfaz

Objetivo declarado: **aspecto de herramienta científica/geoespacial profesional** (registro visual de QGIS, AquaChem, Golden Software Grapher), **no** de notebook ni de dashboard genérico.

### 10.1 Principios

- **Lienzo primero:** el mapa y los diagramas ocupan el máximo espacio; los controles viven en paneles laterales colapsables, no en tarjetas flotantes en medio del contenido.
- **Densidad alta, tipografía pequeña y precisa** (13–14 px de base, tabular para números), no tarjetas grandes con mucho aire.
- **Barra de estado permanente** abajo: nº de muestras cargadas / filtradas / seleccionadas, CRS activo, campaña activa, unidades.
- **Paleta sobria** (grises neutros, un acento) para que el color quede reservado a los datos: grupos, facies, escalas continuas.
- **Nada de emojis** en la interfaz. Los semáforos son símbolos geométricos con color y texto.
- Modo claro y oscuro.

### 10.2 Estructura de navegación

Barra superior fina (identidad, proyecto activo, campaña, acciones globales de importar/exportar) + **rail de iconos vertical a la izquierda** que conmuta el espacio de trabajo:

| Vista | Contenido |
|---|---|
| **Datos** | Tabla maestra, editor de mapeo de columnas, calidad del dato |
| **Validación** | Informe de validación, CBE por muestra, faltantes, duplicados, límites de detección |
| **Piper** | Diagrama grande + panel de control (grupos, color, tamaño, etiquetas, convención) + panel de muestra |
| **Stiff** | Individuales en rejilla · superpuestos por grupo · comparador |
| **Durov / Fisicoquímica** | Durov, pH-TDS, relaciones iónicas |
| **Mapa** | Mapa a pantalla completa + capas + leyenda + selección |
| **Análisis cruzado** | **Vista partida mapa + Piper + tabla sincronizados** (la vista insignia) |
| **Temporal** | Selector de campañas, series, trayectorias. *Deshabilitada con aviso explícito si no hay fechas* |
| **Exportar** | Constructor de exportaciones (formatos, campos, opciones del KMZ) |
| **Reporte** | Vista previa del informe y generación |

### 10.3 Pantalla insignia — "Análisis cruzado"

```
┌───────────────────────────────────────────────────────────────────────────┐
│ HydroChem  ·  Proyecto: Amargosa 2019  ·  Campaña: — (sin fecha) ·  ⤓ ⤒ ⚙ │
├──┬─────────────────────────────────────┬──────────────────────────────────┤
│  │                                     │                                  │
│ 📊│            M A P A                  │        P I P E R                 │
│ ✓ │   puntos por facies / grupo         │   triángulos + rombo             │
│ ◈ │   iconos Stiff opcionales           │   hover y lazo de selección      │
│ ◇ │   selección por lazo                │                                  │
│ ⬡ │                                     │                                  │
│ 🗺│                                     ├──────────────────────────────────┤
│ ⇄ │                                     │  Muestra: Devils Hole            │
│ ⏱ │                                     │  Grupo · Facies · CBE −0,2 %     │
│ ⤓ │                                     │  ┌──────────┐  Ca 50,3  2,51 meq │
│ 📄│                                     │  │  STIFF   │  Mg 20,8  1,71 meq │
│  ├─────────────────────────────────────┴──┴──────────┴───────────────────┤
│  │  TABLA sincronizada — filtros por columna, orden, exportación         │
├──┴───────────────────────────────────────────────────────────────────────┤
│ 90 muestras · 74 filtradas · 1 seleccionada · EPSG:4326 · meq/L          │
└──────────────────────────────────────────────────────────────────────────┘
```

Divisores arrastrables entre los tres paneles; cada panel maximizable a pantalla completa.

### 10.4 Componentes transversales

- **Panel de filtros** (deslizable desde la derecha): grupo, facies, rango de cada parámetro, estado de CBE, excedencias normativas, campaña. Filtros activos visibles como *chips* eliminables.
- **Panel de muestra**: ficha completa, con pestañas mg/L · meq/L · %, miniatura de Stiff, posición en el Piper y —si procede— historial temporal.
- **Botones de exportación** siempre en el mismo sitio: cada vista exporta su gráfico (PNG/SVG) y sus datos (CSV); la exportación completa vive en su propia pantalla.
- **Indicadores de imputación**: todo valor imputado se muestra en cursiva con un marcador discreto y explicación en el tooltip. Nunca se presenta un valor estimado como si fuera medido.

---

## 11. Arquitectura técnica recomendada

### 11.1 Decisiones y justificación

| Capa | Elección | Por qué | Alternativa descartada y motivo |
|---|---|---|---|
| **Núcleo científico** | Paquete Python puro `hydrochem/`, sin dependencias de UI | Todo el valor del notebook está aquí. Aislarlo permite testearlo contra el dataset de 90 sitios como fixture de regresión y reutilizarlo desde la API, desde un CLI o desde otro notebook | Mantenerlo mezclado con la UI: imposible de testear y de auditar científicamente |
| **Backend** | **FastAPI** + Pydantic + Uvicorn | El flujo es *subir archivo → calcular → devolver artefactos* (KMZ, XLSX, PNG). FastAPI da validación por tipos (crítica para datos científicos), `BackgroundTasks` para el KMZ lento, `StreamingResponse` para descargas y OpenAPI gratis. Es Python, así que el núcleo se importa sin fricción | **Streamlit**: la integración cruzada mapa↔Piper es exactamente su punto más débil (re-ejecuta el script y pierde estado de cámara/selección), y no permite la UI profesional que se pide. **Flask**: viable, pero sin validación por tipos ni async de serie; FastAPI no cuesta más |
| **Frontend** | **React + TypeScript + Vite** | La selección cruzada requiere un estado compartido entre 4 vistas; es el problema canónico de React. TypeScript evita errores de contrato con la API en un dominio con decenas de campos numéricos | **Solución 100 % Python** (Dash/Panel): Dash es una opción real, pero el control fino de layout y rendimiento del mapa es peor y el ecosistema de componentes es menor |
| **Estado** | **Zustand** | Mínimo, sin *boilerplate*, ideal para `{data, filters, selection, hover}` | Redux: demasiada ceremonia para este tamaño |
| **Gráficos** | **Plotly.js** | Un solo motor para Piper, Stiff, Durov, dispersión y series; eventos de click/hover/lazo nativos; exporta PNG/SVG; `scattergl` escala a decenas de miles de puntos. Los diagramas ternarios se construyen como `scatter` sobre *shapes*, lo que da control total de la geometría (necesario tras §5.3) | **Matplotlib en el servidor**: imágenes estáticas, adiós interactividad. **D3 puro**: control total pero mucho más trabajo. **`plotly.graph_objects.Scatterternary`**: tentador, pero no permite construir el rombo del Piper ni la disposición de los dos triángulos; hay que hacerlo en coordenadas cartesianas |
| **Mapa** | **MapLibre GL JS** | Vectorial, renderiza en GPU, estilos *data-driven* (color por facies, tamaño por TDS) sin recrear capas, y resalta por estado de *feature* de forma barata — exactamente lo que pide la selección cruzada. Sin licencia de por medio | **Leaflet**: perfectamente válido y más simple; es la alternativa aceptable si el equipo lo prefiere, a costa de peor rendimiento con símbolos complejos y estilos data-driven. **Folium**: genera HTML estático desde Python; incompatible con la interactividad bidireccional. **OpenLayers**: muy capaz pero con una API considerablemente más pesada |
| **Geoproceso** | **pyproj** (obligatorio), **shapely** solo si aparecen geometrías | Reproyección es todo lo que se necesita hoy | **GeoPandas**: 200+ MB de dependencias (GDAL) para lo que hoy resuelven 90 filas de pandas. Añadir solo si entran shapefiles o análisis espacial real |
| **KML/KMZ** | **simplekml** | Ya funciona en el notebook y el popup HTML es reutilizable | Generar KML a mano: reinventar la rueda |
| **Stiff para KMZ** | **SVG generado directamente** (no matplotlib) | 90 figuras matplotlib tardan decenas de segundos; un SVG por muestra se genera en milisegundos, pesa menos y se ve nítido en cualquier escala | Matplotlib: es el cuello de botella actual |
| **Persistencia** | **SQLite + SQLAlchemy** desde el día 1, con el esquema de §6.3 | Cero coste operativo, migración directa a PostgreSQL si crece. Lo importante no es el motor, es **tener ya el esquema multi-fecha** | Ficheros sueltos: impiden preparar la dimensión temporal |
| **Tests** | **pytest** + los 90 sitios como fixture de regresión numérica | El riesgo mayor de un refactor científico es cambiar un resultado sin darse cuenta. Los valores meq/L y CBE del `.xlsm` son un patrón de oro disponible | Sin tests: inaceptable en una herramienta de cálculo |
| **Despliegue** | **Docker**, un contenedor: Uvicorn sirviendo la API y el build estático de React | Un solo artefacto, un solo puerto, reproducible | Dos servicios + proxy: complejidad innecesaria a esta escala |

### 11.2 Alternativa honesta: el camino rápido

Si la prioridad fuera **tener algo usable en días, no en semanas**, existe un camino más corto: **Streamlit + Plotly + `streamlit-folium`**, reutilizando el núcleo `hydrochem/` idéntico. Se conseguiría carga, validación, Piper, Stiff, tabla, mapa y exportaciones en una fracción del tiempo.

Lo que se pierde, y es exactamente lo que el usuario pidió: la selección cruzada real mapa↔Piper y la apariencia de herramienta profesional.

**Recomendación:** construir el núcleo `hydrochem/` primero (fase 1). Ese trabajo es idéntico en ambos caminos. La decisión frontend puede tomarse después, con el cálculo ya funcionando y testeado, sin haber perdido nada.

---

## 12. Código reutilizable vs. código a refactorizar

### A · Reutilizable prácticamente sin cambios

| Elemento | Celda | Observación |
|---|---|---|
| Diccionario `EW` de pesos equivalentes | 14 | Añadir fuente bibliográfica y unificar con el libro Excel (§ R13) |
| Conversión `mg/L ÷ EW` → meq/L | 14 | Vectorizada y correcta |
| Fórmula del CBE | 16 | Validada contra el `.xlsm` |
| Alcalinidad `(HCO₃+CO₃)meq × 50,04` | 18 | Correcta |
| `tri_xy()` | 24 | Verificada analíticamente |
| `draw_tri_grid()` (lógica de isolíneas) | 24 | Las tres familias son exactas |
| `_popup()` — HTML del globo del KMZ | 30 | Buena calidad; solo parametrizar |
| `_v()` — formateo seguro de valores | 30 | |
| Bloque de reproyección con `pyproj` | 10 | Extraer a función, quitar `print` y globals |

### B · Reutilizable tras refactorización

| Elemento | Celda | Qué hay que hacer |
|---|---|---|
| Lector de Excel con detección de formato | 8 | **Corregir `skiprows=[1,2]`** (§R1); devolver objeto de resultado en vez de imprimir; soportar CSV |
| Validación de columnas | 8 | Convertir en mapeo configurable + objeto `ValidationReport` |
| Imputación por mediana de grupo | 12 | Vectorizar (hoy son bucles anidados columna×grupo); **no imputar columnas 100 % vacías**; hacer el método seleccionable; devolver banderas como estructura, no como 10 columnas |
| Flag de fiabilidad | 12 | Umbral configurable |
| `draw_stiff4()` | 20 | La construcción de vértices del polígono es reutilizable; el render matplotlib se sustituye por SVG/Plotly. Parametrizar el orden de iones (el libro Excel lo permite) |
| Stiff superpuestos | 22 | **Código duplicado** de la celda 20: unificar en una sola función |
| Geometría del Piper | 24 | **Corregir el rombo** (§5.3); separar "fondo" (calculado una vez) de "datos"; arreglar el doble etiquetado de porcentajes |
| Detección UTM/DD | 10 | Quitar `UTM_ZONE`/`UTM_HEMI` hardcodeados → CRS declarado por el usuario, con la heurística solo como sugerencia |
| Construcción del KMZ | 30 | Eliminar dependencia de globals (`draw_stiff4`, `gcolors`, `_XLIM`); mover a servicio asíncrono; sustituir matplotlib por SVG |
| Tabla resumen | 32 | Selección de columnas configurable |
| Análisis de flúor | 28 | Generalizar a "cualquier parámetro contra cualquier umbral normativo"; **usar `lon_wgs84`/`lat_wgs84`** (§R10) |

### C · Reemplazable

| Elemento | Celda | Sustituto |
|---|---|---|
| `!pip install -q ...` | 2 | `pyproject.toml` / `requirements.txt` con versiones fijadas |
| `from google.colab import files` | 2 | — |
| `files.upload()` | 6 | Endpoint `POST /datasets` + componente de subida |
| `files.download()` | 4, 34 | `StreamingResponse` / enlaces de descarga |
| Generación de la plantilla dentro del notebook | 4 | Endpoint `GET /template.xlsx` (la lógica openpyxl se conserva) |
| `warnings.filterwarnings('ignore')` | 2 | Logging real; silenciar avisos oculta problemas de datos |
| `print()` con emojis como informe | todas | Objetos Pydantic + pantallas de la UI |
| Durov (celda 26) | 26 | **Rehacer**: los marginales no tienen contorno, el eje Y está mal etiquetado y el panel pH está vacío |
| Mapa de flúor en matplotlib | 28 | Mapa web interactivo |
| Empaquetado ZIP + descarga | 34 | Constructor de exportaciones |
| Numeración manual de secciones | markdown | Rutas de la aplicación |

### D · A desarrollar desde cero

| Funcionalidad | Prioridad | Comentario |
|---|---|---|
| **Clasificación de facies hidroquímicas** | MVP/V2 | No existe **nada** hoy. Es lo que convierte un gráfico en un análisis |
| Validación de datos real (rangos, duplicados, unidades, límites de detección) | MVP | Hoy solo se comprueba la presencia de columnas |
| Parseo de límites de detección (`<0,05`) | MVP | Hoy se convierten en `NaN` indistinguibles de "no medido" |
| Modelo de datos y persistencia | MVP | Con `sampled_at` desde el primer día |
| API | MVP | |
| Interfaz web completa | MVP | |
| Mapa interactivo | MVP | |
| Selección cruzada mapa ↔ Piper | V2 | |
| Exportación GeoJSON / KML / CSV | MVP | Hoy solo hay KMZ y XLSX |
| Módulo temporal | V2 (inactivo hasta tener fechas) | |
| Umbrales normativos configurables | V2 | Hoy solo `WHO_F = 1.5`, duplicado en dos celdas |
| Relaciones iónicas, Gibbs, SAR | V2/V3 | |
| Reporte PDF/HTML | V2 | |
| Suite de tests | MVP | |
| Registro de procedencia (qué es medido, derivado o imputado) | MVP | Parcialmente existe con las banderas `*_imputed`; hay que generalizarlo |

---

## 13. Riesgos y problemas detectados

### Críticos

**R1 · Pérdida silenciosa de la primera fila de datos**
`pd.read_excel(fname, header=0, skiprows=[1, 2])` descarta la fila de descripciones **y** la fila siguiente. Si el usuario sustituye la fila de ejemplo por datos reales, esa muestra desaparece sin aviso.
*Evidencia:* la hoja `DATA` tiene **90** sitios; el notebook informa `Loaded 89 samples`; falta *Amargosa Tracer Well 2*; el recuento de excedencias de flúor es **31** en el notebook frente a **32** en el origen (el sitio perdido tiene F = 1,7 mg/L).
*Corrección:* detectar la fila de descripciones por contenido y saltar **solo esa fila**.

**R2 · Geometría del rombo del Piper incorrecta**
Ver §5.3. El rombo se dibuja con el doble de tamaño y centrado 1,04 unidades por debajo de su posición; invade ambos triángulos. Cualquier lectura del diagrama es engañosa.

**R3 · `F⁻ = 0` tratado como medición real**
32 de 90 muestras tienen F exactamente 0. El manual del libro Excel documenta explícitamente (changelog v5) que las **celdas vacías se tratan como 0**, es decir: **0 significa "no medido"**, no "ausente". El notebook lo toma como valor real → el boxplot por grupo, el gráfico F vs Ca y la escala de color del mapa están sesgados a la baja, y el denominador del informe de excedencias (31/89) mezcla medidos y no medidos.
*Corrección:* tratar los ceros de F como faltantes salvo que el usuario declare lo contrario, y exigir una columna de "no detectado / límite de detección".

**R4 · NO₃⁻ imputado a cero y contabilizado**
NO₃ está 100 % ausente. La cascada de imputación (mediana de grupo → mediana global → `0.0`) le asigna 0 a las 89 muestras y lo marca como imputado. Ese 0 entra después en `sum_an`, en el CBE, en el vértice `Cl+F+NO₃` del Piper y en la fila `F+NO₃` del Stiff. El efecto numérico aquí es nulo (0 es 0), **pero la lógica es peligrosa**: una columna parcialmente vacía recibiría medianas globales sin sentido geoquímico.
*Corrección:* si una columna está 100 % vacía, excluirla del análisis y decirlo, en lugar de imputarla.

**R5 · Ausencia total de dimensión temporal**
No es un bug, es una **restricción de los datos** que condiciona el alcance. Debe gobernar el diseño (§6.3) y debe comunicarse con claridad en la interfaz. El riesgo real es que alguien intente rellenarla artificialmente.

### Altos

**R6 · Orientación no estándar de los ternarios**
Na+K en el ápice catiónico y Cl+F+NO₃ en el aniónico, en lugar de Mg y SO₄. Impide superponer las plantillas clásicas de clasificación. Hay que decidir la convención **antes** de implementar facies (§5.4).

**R7 · pH, temperatura y OD ausentes y nunca imputados**
`PHYS_COLS` no entra en la imputación. Con este dataset están 100 % vacíos → el panel "pH vs TDS" del Durov sale **completamente vacío** (visible en la salida ejecutada) y cualquier análisis fisicoquímico es inviable. La aplicación debe **desactivar** las vistas que dependen de datos ausentes y explicarlo, no dibujar ejes vacíos.

**R8 · Nombres de columna fijos, sin mapeo**
`REQUIRED_COLS` exige 17 nombres exactos. El usuario real ya tuvo que hacer un trasvase manual del `.xlsm` a la plantilla. Sin mapeo configurable, el problema se repetirá con cada fuente nueva.

**R9 · Sin manejo de límites de detección**
`pd.to_numeric(errors='coerce')` convierte `"<0.05"`, `"n.d."` o `"ND"` en `NaN`, que después se imputa. Se pierde la información de que **sí se midió** y estuvo por debajo del límite. El propio notebook discute el método "medio-LD" en su celda markdown 11 pero **no lo implementa**.

**R10 · Mezcla de coordenadas crudas y reproyectadas**
La celda 28 dibuja con `Longitude`/`Latitude`; la celda 30 exporta con `lon_wgs84`/`lat_wgs84`. Con entrada UTM, mapa y KMZ discrepan.

### Medios

**R11 · Dependencia del orden de ejecución y variables globales**
`draw_stiff4`, `gcolors`, `group_list`, `_XLIM`, `ROWS`, `_LEFT_LABELS` se definen en la celda 20 y se usan en las celdas 22 y 30. `df` se reasigna en cadena (`df_probe` → `df_raw` → `df` → `df_imputed` → `df`). Ejecutar fuera de orden falla o produce resultados distintos. En una aplicación, esto debe ser paso de parámetros explícito.

**R12 · Rendimiento de la generación del KMZ**
Una figura matplotlib por muestra (90 hoy, potencialmente miles). Decenas de segundos, bloqueante. Debe ser asíncrono y/o SVG.

**R13 · Pesos equivalentes inconsistentes entre notebook y libro Excel**
HCO₃: 61,017 vs 61 · CO₃: 30,004 vs 30 · F: 19,00 vs 18,9984 · Mg: 12,155 vs 12,156. Diferencias <0,1 %, irrelevantes en la práctica, pero hay que fijar **una** tabla canónica con fuente citada, o los resultados no serán reproducibles bit a bit entre herramientas.

**R14 · Grupos muy pequeños**
"Well AD-4 corridor" tiene 2 muestras y "Furnace Creek" 3. La mediana de grupo como método de imputación es frágil con n≤3, y cualquier estadístico por grupo debe mostrar n y advertirlo.

**R15 · El nombre del sitio como clave**
`Site` es texto libre. El propio manual del libro Excel documenta que desduplica nombres repetidos añadiendo un sufijo numérico — prueba de que ocurre en la práctica. Con datos multi-fecha, una clave textual se rompe.

**R16 · `_imputed` nunca se detecta en los Stiff individuales**
Celda 20: `has_imp = bool(row.get('_imputed', False))`. No existe ninguna columna llamada `_imputed` (se llaman `Ca_imputed`, `Mg_imputed`…), así que **siempre es `False`** y el resaltado de muestras imputadas (borde discontinuo y fondo ámbar) nunca se activa. En la celda 30 (KMZ) la misma comprobación **sí** está bien escrita.

### Bajos

- **R17** · Etiquetas de porcentaje duplicadas en los bordes inferiores de los triángulos (`add_pct_ticks` escribe `p` y `1−p` en el mismo borde).
- **R18** · La leyenda del Durov se dibuja encima de los datos.
- **R19** · La carpeta "Legend" del KMZ coloca placemarks en (0, 0), en el Golfo de Guinea.
- **R20** · Dos secciones numeradas "14" en el markdown.
- **R21** · `scipy` se instala pero nunca se usa; `KNNImputer` se importa pero solo aparece en código comentado.
- **R22** · `WHO_F` definido dos veces (celdas 28 y 30).
- **R23** · `warnings.filterwarnings('ignore')` oculta avisos legítimos de pandas sobre los datos.
- **R24** · Si el DataFrame quedara vacío, la variable `i` del bucle de la celda 20 no estaría definida y el código fallaría con `NameError`.

---

## 14. Estructura de carpetas propuesta

Diseñada a partir del código real encontrado: un núcleo científico aislado (porque es lo único verdaderamente valioso del notebook y lo único que hay que proteger con tests), una API fina encima, y un frontend independiente.

```
hydrochem-web/
├── README.md
├── pyproject.toml                 # dependencias fijadas, sin !pip install
├── docker-compose.yml
├── Dockerfile
│
├── core/                          # ← NÚCLEO CIENTÍFICO. Sin FastAPI, sin UI.
│   └── hydrochem/
│       ├── __init__.py
│       ├── constants.py           # EW (con fuente citada), umbrales OMS/locales,
│       │                          #   catálogo de iones, familias de facies
│       ├── io/
│       │   ├── readers.py         # Excel/CSV; corrige R1; detecta fila de descripciones
│       │   ├── column_mapping.py  # mapeo configurable  ← resuelve R8
│       │   ├── detection_limits.py# parseo de "<0,05", "ND"  ← resuelve R9
│       │   └── template.py        # generación de la plantilla (de la celda 4)
│       ├── validation/
│       │   ├── schema.py          # modelos Pydantic de una muestra
│       │   ├── rules.py           # rangos, duplicados, coherencia de unidades
│       │   └── report.py          # ValidationReport estructurado (sustituye los print)
│       ├── chemistry/
│       │   ├── units.py           # mg/L ↔ meq/L ↔ mmol/L     [celda 14 · A]
│       │   ├── balance.py         # CBE                        [celda 16 · A]
│       │   ├── alkalinity.py      # alcalinidad como CaCO₃     [celda 18 · A]
│       │   ├── ratios.py          # Na/Cl, Ca/Mg, Gibbs, SAR   [NUEVO]
│       │   └── facies.py          # clasificación hidroquímica [NUEVO]
│       ├── imputation/
│       │   ├── strategies.py      # none / group-median / KNN / half-DL
│       │   └── flags.py           # registro de procedencia     ← resuelve R4
│       ├── geometry/
│       │   ├── ternary.py         # tri_xy + rejillas           [celda 24 · A]
│       │   ├── piper.py           # geometría CORREGIDA §5.3    [celda 24 · B]
│       │   ├── stiff.py           # vértices del polígono       [celda 20 · B]
│       │   └── durov.py           # rehecho                     [celda 26 · C]
│       ├── geo/
│       │   ├── crs.py             # pyproj; CRS explícito       [celda 10 · A/B]
│       │   └── exporters/
│       │       ├── geojson.py     # [NUEVO]
│       │       ├── kml.py         # [NUEVO]
│       │       ├── kmz.py         # simplekml + _popup          [celda 30 · B]
│       │       └── stiff_svg.py   # SVG en lugar de matplotlib  ← resuelve R12
│       └── pipeline.py            # orquestación de extremo a extremo
│
├── backend/
│   └── app/
│       ├── main.py
│       ├── api/v1/
│       │   ├── datasets.py        # subida, listado, borrado
│       │   ├── validation.py
│       │   ├── analysis.py        # meq/L, CBE, alcalinidad, facies
│       │   ├── diagrams.py        # coordenadas de Piper/Stiff/Durov (JSON, no PNG)
│       │   ├── spatial.py         # GeoJSON de las estaciones
│       │   ├── temporal.py        # inactivo mientras no haya fechas
│       │   └── exports.py         # CSV/XLSX/GeoJSON/KML/KMZ
│       ├── models/                # SQLAlchemy: stations, samples, results, campaigns
│       ├── schemas/               # Pydantic de entrada/salida
│       ├── services/
│       │   ├── dataset_service.py
│       │   └── export_service.py  # tareas en segundo plano (KMZ)
│       └── db.py
│
├── frontend/
│   ├── index.html
│   ├── vite.config.ts
│   └── src/
│       ├── main.tsx
│       ├── api/                   # cliente tipado generado desde OpenAPI
│       ├── store/                 # Zustand: data, filters, selection, hover
│       ├── layouts/               # AppShell, rail lateral, barra de estado
│       ├── views/
│       │   ├── DataView.tsx
│       │   ├── ValidationView.tsx
│       │   ├── PiperView.tsx
│       │   ├── StiffView.tsx
│       │   ├── DurovView.tsx
│       │   ├── MapView.tsx
│       │   ├── CrossAnalysisView.tsx   # la pantalla insignia
│       │   ├── TemporalView.tsx        # con estado "sin fechas"
│       │   └── ExportView.tsx
│       ├── components/
│       │   ├── charts/            # PiperChart, StiffChart, DurovChart, TimeSeries
│       │   ├── map/               # MapCanvas, LayerControl, StiffMarker
│       │   ├── table/             # DataTable con filtros por columna
│       │   └── panels/            # SamplePanel, FilterPanel, LegendPanel
│       └── styles/                # tokens de diseño, tema claro/oscuro
│
├── data/
│   ├── samples/                   # datasets de ejemplo (los 90 sitios de Amargosa)
│   └── uploads/                   # subidas de usuario (fuera de git)
│
├── exports/                       # artefactos generados (fuera de git)
│
├── tests/
│   ├── fixtures/
│   │   └── amargosa_90.csv        # ← patrón de oro extraído del .xlsm
│   ├── test_units.py              # meq/L contra las columnas R–Z del .xlsm
│   ├── test_balance.py            # CBE contra la columna Q del .xlsm
│   ├── test_piper_geometry.py     # vértices contra la hoja CONTROL
│   ├── test_readers.py            # regresión de R1: 90 filas entran, 90 salen
│   ├── test_imputation.py         # regresión de R4: columna vacía no se imputa
│   └── test_exports.py            # el KMZ abre y contiene N placemarks
│
└── docs/
    ├── AUDITORIA-FASE-0.md        # este documento
    ├── METHODOLOGY.md             # fórmulas, pesos equivalentes, fuentes
    ├── DATA-DICTIONARY.md         # esquema de entrada y de salida
    └── API.md
```

---

## 15. Plan de implementación por fases

### FASE 0 — Auditoría y especificación ✅ completada

Este documento. Productos: inventario de datos, reconstrucción del flujo, catálogo de 24 riesgos, geometría correcta del Piper especificada, esquema multi-fecha definido.

---

### FASE 1 — Núcleo científico

- **Objetivo:** convertir el cálculo del notebook en un paquete Python testeado, independiente de la UI.
- **Tareas:** extraer el fixture `amargosa_90.csv` desde el `.xlsm`; portar `units`, `balance`, `alkalinity`; portar `ternary` y **corregir la geometría del Piper (§5.3)**; portar la geometría del Stiff unificando las celdas 20 y 22; reescribir la imputación (vectorizada, sin imputar columnas vacías); fijar la tabla canónica de pesos equivalentes con fuente; escribir los tests de regresión contra las columnas R–Z y Q del `.xlsm`.
- **Módulos:** `core/hydrochem/{constants,chemistry,geometry,imputation}`, `tests/`
- **Dependencias:** ninguna.
- **Resultado:** `pytest` en verde reproduciendo los valores del libro Excel.
- **Dificultad:** media-baja. **Riesgos:** R2, R4, R13, R14.

---

### FASE 2 — Entrada, validación y modelo de datos

- **Objetivo:** que cualquier Excel/CSV razonable entre sin trasvase manual, y que la dimensión temporal quede preparada.
- **Tareas:** lector con **corrección de R1**; mapeo configurable de columnas; parseo de límites de detección; reglas de validación (rangos plausibles por ion, duplicados, CBE, unidades, coordenadas); `ValidationReport` estructurado; **esquema SQLAlchemy de §6.3 con `sampled_at` y `campaign_id` desde el primer día**; plantilla `.xlsx` con `Sampled_Date` y `Campaign` opcionales.
- **Módulos:** `core/hydrochem/{io,validation}`, `backend/app/models`
- **Dependencias:** F1.
- **Resultado:** los 90 sitios del `.xlsm` se cargan **directamente**, sin trasvase, y salen 90 (no 89).
- **Dificultad:** media. **Riesgos:** R1, R3, R8, R9, R15.

---

### FASE 3 — API

- **Objetivo:** exponer el núcleo por HTTP.
- **Tareas:** FastAPI; endpoints de datasets, validación, análisis y diagramas (devolviendo **coordenadas en JSON**, no imágenes); OpenAPI; cliente TypeScript generado.
- **Dependencias:** F1, F2.
- **Resultado:** `POST /datasets` + `GET /datasets/{id}/piper` devuelven los puntos listos para dibujar.
- **Dificultad:** baja. **Riesgos:** definir bien el contrato del objeto muestra (§8.2) — un cambio posterior se propaga a todo el frontend.

---

### FASE 4 — Piper interactivo

- **Objetivo:** el producto estrella.
- **Tareas:** `PiperChart` en Plotly con el fondo como *shapes*; hover con ficha; click y lazo de selección; color por grupo; conmutador de convención de orientación (§5.4); exportación PNG/SVG; **clasificación de facies** (empezar por la clásica de Piper).
- **Dependencias:** F3.
- **Resultado:** Piper correcto, interactivo y con facies.
- **Dificultad:** media. **Riesgos:** R2 (ya resuelto en F1), R6 — decidir la convención antes de codificar la clasificación.

---

### FASE 5 — Stiff, Durov y fisicoquímica

- **Objetivo:** el resto de diagramas.
- **Tareas:** Stiff individuales y superpuestos; orden de iones configurable; escala común o por grupo; **Durov rehecho** (marginales con contorno, ejes correctos, pH y TDS reales); desactivación explícita de vistas cuyos datos no existan (**R7**); relaciones iónicas.
- **Dependencias:** F4.
- **Dificultad:** media. **Riesgos:** R7.

---

### FASE 6 — Mapa interactivo

- **Tareas:** MapLibre; capa GeoJSON; estilos data-driven por grupo/facies/parámetro; popup; marcadores de Stiff en SVG; capas base; leyenda; **CRS explícito** en lugar de la heurística hardcodeada; selección por lazo.
- **Dependencias:** F3.
- **Dificultad:** media. **Riesgos:** R10, rendimiento de los marcadores SVG con muchos puntos.

---

### FASE 7 — Integración cruzada

- **Objetivo:** la pantalla insignia.
- **Tareas:** estado compartido en Zustand; sincronización bidireccional mapa↔Piper↔Stiff↔tabla; resaltado mediante `Plotly.restyle` y estado de *feature* de MapLibre; layout de paneles redimensionables.
- **Dependencias:** F4, F5, F6.
- **Dificultad:** **alta** — es la parte técnicamente más exigente del proyecto. **Riesgos:** rendimiento del re-render, bucles de eventos entre componentes.

---

### FASE 8 — Exportación

- **Tareas:** CSV, XLSX, GeoJSON, KML; **KMZ** con Stiff en SVG y `_popup` reutilizado; constructor de exportaciones; **tarea asíncrona con progreso**; eliminar la carpeta "Legend" en (0,0); forzar punto decimal.
- **Dependencias:** F6.
- **Resultado:** KMZ que abre en Google Earth Pro con los 90 sitios agrupados y con Stiff.
- **Dificultad:** media-baja. **Riesgos:** R12, R19.

---

### FASE 9 — Módulo temporal *(condicionada)*

- **Objetivo:** activar el análisis temporal **cuando existan ≥2 campañas reales**.
- **Tareas:** selector de campañas; Piper por fecha y por periodo; trayectorias de estación en el Piper; series por parámetro; comparación entre estaciones; matriz de transición de facies.
- **Dependencias:** F2 (esquema) + **datos reales con fecha**.
- **Resultado:** con los datos actuales, una pantalla que explica claramente que no hay fechas registradas y qué haría falta.
- **Dificultad:** media. **Riesgo principal: intentar construir esto antes de tener datos** y acabar validándolo contra fechas inventadas.

---

### FASE 10 — UX final y reporte

- **Tareas:** tema claro/oscuro; densidad y tipografía científica; accesibilidad; panel de filtros; estados vacíos y de error informativos; **reporte HTML/PDF** con gráficos y tablas; ayuda contextual con las fórmulas y sus fuentes.
- **Dependencias:** F7.
- **Dificultad:** media.

---

### FASE 11 — Pruebas y aseguramiento

- **Tareas:** completar la cobertura del núcleo; pruebas de contrato de la API; pruebas de componentes del frontend; **una prueba de extremo a extremo con el `.xlsm` real**; validación cruzada Piper/Stiff/CBE contra el libro Excel; CI.
- **Dependencias:** todas.
- **Dificultad:** media.

---

### FASE 12 — Despliegue

- **Tareas:** Dockerfile multi-etapa; variables de entorno; copias de seguridad de la base; documentación de instalación; opcionalmente un ejecutable de escritorio.
- **Dificultad:** baja.

---

### Camino crítico

```
F1 ─→ F2 ─→ F3 ─┬─→ F4 ─→ F5 ─┐
                └─→ F6 ───────┴─→ F7 ─→ F10 ─→ F11 ─→ F12
                    └─→ F8
                        F9  (bloqueada por disponibilidad de datos)
```

---

## 16. MVP recomendado

**Construir primero, y solo:** F1 + F2 + F3 + F4 (sin facies avanzada) + F6 + F8 (CSV/XLSX/GeoJSON/KMZ).

Es decir, una aplicación que:

1. acepta el `.xlsm` original **o** cualquier Excel/CSV con mapeo de columnas;
2. valida y explica qué hay, qué falta y qué es fiable;
3. calcula meq/L, CBE y alcalinidad, con trazabilidad de lo imputado;
4. dibuja un **Piper interactivo correcto** con hover y selección;
5. muestra un **mapa interactivo** con los puntos y su ficha;
6. exporta **KMZ para Google Earth**, GeoJSON, CSV y XLSX.

**Por qué este recorte:** cubre el ciclo completo *dato crudo → análisis → producto entregable* y ya aporta más que el notebook (sin el bug de la fila perdida, con el Piper bien dibujado, sin Colab y sin trasvase manual). Deja fuera lo caro (F7, integración cruzada) y lo que no se puede validar todavía (F9, temporal).

**Fuera del MVP, deliberadamente:** Durov, análisis temporal, selección cruzada completa, reporte PDF, facies avanzadas, índices de saturación, multiusuario.

---

## 17. Próximos pasos — qué hacer exactamente en la siguiente etapa

1. **Decidir tres cuestiones abiertas** (bloquean decisiones de diseño, no de código):
   - **Convención de orientación del Piper** (§5.4): ¿clásica con Mg y SO₄ en los ápices, o la del notebook? Recomendación: clásica, con la del notebook como opción.
   - **Tratamiento de `F = 0`** (§R3): ¿es "no medido" o es un cero real? De la respuesta depende todo el análisis de flúor.
   - **Camino del frontend** (§11.2): React (recomendado, cumple lo pedido) o Streamlit (rápido, con pérdidas conocidas). No es urgente: la fase 1 es idéntica en ambos casos.

2. **Extraer el patrón de oro.** Volcar las filas 15–104 de la hoja `DATA` del `.xlsm` a `tests/fixtures/amargosa_90.csv`, **incluyendo las columnas Q y R–Z** (balance de carga y meq/L calculados por Excel). Son el testigo contra el que se validará todo el núcleo científico.

3. **Arrancar la FASE 1**, con esta secuencia de commits:
   1. `constants.py` — pesos equivalentes con fuente citada.
   2. `chemistry/units.py` + `test_units.py` contra las columnas R–Z.
   3. `chemistry/balance.py` + `test_balance.py` contra la columna Q.
   4. `chemistry/alkalinity.py`.
   5. `geometry/ternary.py` (portado tal cual, ya verificado).
   6. `geometry/piper.py` **con la geometría corregida** + `test_piper_geometry.py` contra los vértices de la hoja `CONTROL` (1,15·0,2598 / 0,65·1,1258 / 1,15·1,9919 / 1,65·1,1258 con hueco 0,3).
   7. `geometry/stiff.py` unificando las celdas 20 y 22.
   8. `imputation/` con la regla "no imputar columnas 100 % vacías" + su test de regresión.

4. **No hacer todavía:** nada de frontend, nada de mapa, nada temporal. Y bajo ningún concepto generar fechas sintéticas.

---

## Anexo · Supuestos declarados

1. **Supongo** que las coordenadas del `.xlsm` son WGS84 geográficas (EPSG:4326). No está declarado en el archivo; lo deduzco del rango de valores y de la región (Death Valley, Nevada/California). **Debe confirmarse.**
2. **Supongo** que el archivo realmente cargado en la ejecución registrada del notebook contenía los datos de la hoja `DATA` del `.xlsm`, trasvasados a mano. La coincidencia de los 7 grupos, de los nombres de sitio, de los valores y del recuento (90 → 89 por el bug R1) lo hace prácticamente seguro, pero el archivo intermedio no se ha aportado.
3. **Supongo** que los `F = 0` significan "no medido" —así lo documenta el manual del libro Excel para las celdas vacías— y no una concentración real de cero. **Requiere confirmación del usuario** (§17.1).
4. **Supongo** que el destino del KMZ es Google Earth Pro de escritorio, tal como indica el propio notebook y el manual del libro Excel.
5. **Supongo** que el dataset de Amargosa es material de referencia/ejemplo y que la herramienta se usará con otros datos —probablemente de Perú, dado el contexto del usuario—, por lo que el mapeo de columnas y el CRS configurable son requisitos, no adornos.
6. **No supongo nada** sobre fechas de muestreo: no existen, y el diseño lo refleja.
