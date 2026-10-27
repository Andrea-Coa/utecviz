# UtecVis by Batimix — Instrucciones para el agente de código

> Este documento complementa el enunciado de la tarea (se entrega aparte). Si algo aquí contradice el enunciado, **manda el enunciado**. Restricciones duras del enunciado: **solo D3** para visualizar (ninguna otra librería de gráficos), **aplicación Flask**, entrega en **un ZIP** con la app y los archivos de datos (**nodos y aristas**), **mínimo 4 tareas**, **interacción y animación obligatorias**, una **única visualización de red**.

---

## 1. Objetivo

Construir una página web, **"UtecVis by Batimix"**, cuyo centro es **una sola visualización de red** de los docentes e investigadores de UTEC. La red debe revelar:

- quién colabora más,
- quién conecta departamentos (puentes),
- si los grupos naturales de colaboración coinciden con los departamentos,
- qué colaboraciones nuevas son probables.

Existe un **prototipo funcional** (`prototipo_utecvis_v2.html`, con datos simulados) que define el comportamiento esperado. Úsalo como **referencia funcional** de las interacciones y codificaciones, no como base de código: la versión oficial debe estar bien estructurada, usar datos reales y precalcular todo lo posible.

---

## 2. Público objetivo

**Principal: la Dirección de Investigación y los jefes de departamento de UTEC.** Necesitan:

- ver de un vistazo la estructura de colaboración interna,
- identificar a las personas clave (las más prolíficas y los conectores),
- detectar silos,
- encontrar oportunidades para fomentar colaboraciones interdisciplinarias.

**Secundario: docentes e investigadores** que buscan coautores con intereses afines fuera de su departamento, y **estudiantes de posgrado** que buscan asesor.

Implicaciones de diseño:

- Usuarios no técnicos en redes: cada codificación debe explicarse en la propia página (bloque "Cómo leer la red").
- Nada de jerga sin traducir: "betweenness" se acompaña de "qué tan puente es".
- La página debe sostenerse sola, sin presentador, como pide el enunciado.

---

## 3. Tareas de visualización (las 4 obligatorias)

| # | Pregunta | Métrica | Codificación principal |
|---|---|---|---|
| **T1** | ¿Quiénes son los colaboradores más prolíficos dentro de UTEC? | Grado ponderado (publicaciones compartidas con otros docentes UTEC) | **Tamaño del nodo** (siempre visible, escala fija) + ranking en el panel |
| **T2** | ¿Quiénes actúan como puentes entre departamentos? | Betweenness centrality + fracción de coautorías fuera del departamento | **Anillo oscuro** alrededor del nodo (grosor ∝ betweenness, activable/desactivable) + **posición entre zonas** (layout) + aristas entre departamentos más oscuras |
| **T3** | ¿Los grupos naturales de colaboración coinciden con los departamentos? | Comunidades Louvain, modularidad Q, NMI comunidad↔departamento, "pureza" por comunidad | Botón **Agrupar por: Departamento \| Comunidad**: los nodos se reordenan con transición animada; el color sigue siendo el departamento |
| **T4** | ¿Qué colaboraciones nuevas son probables, sobre todo entre departamentos? | Similitud coseno entre embeddings de su producción, en pares **sin** coautoría (opcionalmente combinada con Adamic-Adar) | Botón **Colaboraciones potenciales**: atenúa las coautorías y dibuja aristas punteadas; slider de umbral; filtro "solo entre departamentos" |

**Tarea transversal (animación):** ¿cómo evolucionó la red de colaboración en el tiempo? Un slider de año y un botón ▶ construyen la red año a año (por ejemplo, 2012→2026), con todas las métricas recalculadas para cada año (**precalculadas**, ver §6).

---

## 4. Datos de entrada

Coloca los archivos (obtenidos por web scraping de `https://cris.utec.edu.pe/es/persons/`) en `utecviz/data/raw/`:

**De `utec_perfiles.zip`:**

- `perfiles.csv`: una fila por persona (104). Columnas: nombre, cargos, email, orcid, telefono, direccion, google_scholar, linkedin, scopus, otros_links, citas, indice_h, perfil_profesional, educacion, temas_interes, calificacion_renacyt, posiciones_externas, n_publicaciones, huella_digital_top10, archivo_foto, foto_url, url_perfil.
- `publicaciones.csv`: lista corta de publicaciones por persona.
- `huella_digital.csv`: con las columnas investigador, concepto, area y peso. **Ojo:** el peso es relativo dentro de cada persona (el concepto principal vale 100%). No es comparable entre personas ni suma 100%.
- `datos_completos.json`: todo lo anterior, estructurado.
- `fotos/`: 104 fotos de perfil, nombradas por el slug del perfil.

**De `utec_publicaciones_detalle.zip`:**

- `publicaciones_detalle.csv` y `publicaciones_detalle.json`: 2.479 publicaciones únicas, con título, tipo, autores, `investigadores_utec_perfil`, `autores_utec` (con URL de perfil), resumen, propiedades (revista, volumen, DOI, ISSN/ISBN, estado con año, conferencia…), huella y BibTeX.
- `publicacion_investigador.csv`: 2.976 filas con las columnas investigador, titulo, tipo, anio, doi y url. **Es la tabla puente para construir la red de coautoría.**

**Identificador de nodo:** usa el **slug** del perfil, el último segmento de `url_perfil`, decodificado de URL (hay tildes y ñ codificadas como `%C3%A9`). Enlaza personas↔publicaciones por **nombre exacto del perfil**, que es el mismo en ambas fuentes, y verifica que el 100% de las filas cruce. Reporta las que no crucen.

---

## 5. Procesamiento de datos (pipeline offline en Python)

Todo el procesamiento pesado se hace **una vez, offline**, en scripts numerados. La app Flask solo sirve archivos ya calculados.

```
utecviz/pipeline/
  01_limpieza.py        # personas, departamentos, educación, métricas bibliométricas
  02_coautoria.py       # aristas de coautoría (con años)
  03_embeddings.py      # vectores por persona + matriz de similitud
  04_metricas.py        # métricas de red por año, comunidades, NMI
  05_exportar.py        # JSON/CSV finales + miniaturas de fotos
```

### 5.1 Personas (`01_limpieza.py`)

- **Departamento:** se extrae de `cargos`, que separa varios cargos con `|`. Busca el patrón `Departamento de …`. Si hay varios, el **departamento principal** es el primero; guarda todos en `departamentos`. Si no hay ninguno, intenta con `Facultad`, `Escuela` o `Centro`. Si aún falta, asigna `"Sin departamento"` y **lista esos casos en un reporte** (`data/processed/reporte_calidad.md`) para revisión manual con un diccionario de corrección (`data/manual/departamentos_override.csv`).
- **Normaliza los nombres de departamento:** strip, espacios, mayúsculas y variantes con o sin tilde. Cuenta cuántos departamentos quedan (ver §7.3 sobre colores).
- **Grado académico máximo**, a partir de `educacion`: Doctorado (Doctor, PhD, Ph.D., Doctorado) > Maestría (Máster, Master, Magíster, MSc, Maestría) > Título profesional / Licenciatura > Bachiller > Desconocido.
- **Numéricos:** `citas` e `indice_h` vienen como texto y pueden usar `.` como separador de miles. Convierte a entero; si está vacío, usa `null`, no 0.
- **Temas:** une `temas_interes`, los conceptos de la huella y `perfil_profesional` para el panel de detalle y para el texto de embeddings.
- **No muestres emails ni teléfonos en la UI** (no aportan a las tareas). ORCID, Scholar y Scopus sí pueden ir como enlaces en la ficha.

### 5.2 Publicaciones y coautoría (`02_coautoria.py`)

- **Deduplica las publicaciones por `url`.**
- **Año:** usa la columna `anio` o extráelo de `propiedades.Estado` con el regex `(19|20)\d{2}`. Si no hay año, la publicación cuenta para 2026 pero no para la animación (márcala con `year=null`).
- **Número de autores:** sale del campo `autores` (separado por comas y `&`). Marca como **hiperautoría** las publicaciones con más de 50 autores: hay colaboraciones de física con miles de autores y un investigador con 1.132 publicaciones.
- **Arista de coautoría** entre dos docentes UTEC si comparten al menos una publicación. Para cada par guarda:
  - `w`: número de publicaciones compartidas (peso principal);
  - `w_frac`: suma de `1/(n_autores-1)` por publicación (peso fraccional, que atenúa la hiperautoría);
  - `first_year` y `w_by_year` (conteo por año, para la animación acumulada);
  - `cross`: `true` si los departamentos principales difieren;
  - `pubs`: lista de las URLs compartidas (para el detalle).
- **Parámetro de configuración** `EXCLUIR_HIPERAUTORIA` (por defecto `False`). Documenta en el README el efecto que tiene sobre las métricas.
- **Productividad individual** (para el panel, no para el tamaño):
  - `pubs_total`;
  - `pubs_por_anio_activo` = publicaciones / (2026 − primer año + 1);
  - `pubs_fraccional` = Σ 1/n_autores.
- Las personas sin coautores UTEC **se mantienen** como nodos aislados.

### 5.3 Embeddings y similitud (`03_embeddings.py`)

**Texto por persona:**

1. **Embedding de cada publicación:** título + resumen (si no hay resumen, solo el título).
2. **Vector de la persona** = promedio ponderado de los embeddings de sus publicaciones. El peso es mayor para las recientes, por ejemplo `exp(-(2026-año)/8)`, y se reduce para la hiperautoría (por ejemplo, usar el peso fraccional).
3. **Embedding del perfil:** perfil profesional + temas de interés + conceptos de la huella.
4. **Vector final** = `0.75·pubs + 0.25·perfil`, normalizado L2. Si no hay publicaciones, usa solo el perfil. Si no hay nada, la persona no tiene vector (`null`) y no participa en T4; repórtala.

**Modelos sugeridos.** El corpus es mayormente inglés, con perfiles en español, así que conviene un modelo multilingüe:

| Modelo | Por qué | Notas |
|---|---|---|
| **`BAAI/bge-m3`** *(recomendado)* | Multilingüe, fuerte en recuperación semántica, admite textos largos (8k tokens) | ~570M parámetros; en CPU tarda unos minutos para ~2.500 textos. Correr una vez y cachear. |
| `intfloat/multilingual-e5-base` (o `-large`) | Multilingüe, muy buen balance calidad/velocidad | Requiere el prefijo `"passage: "` en cada texto. |
| `allenai/specter2_base` (+ adaptador `proximity`) | Entrenado con artículos científicos (título+abstract): ideal para similitud entre papers | Solo inglés. Úsalo para las publicaciones y un multilingüe para los perfiles. |
| `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | Ligero y multilingüe, buena línea base | Menor calidad en textos científicos largos. |

Usa `sentence-transformers`. **Cachea los embeddings** en `data/processed/emb_pubs.npy` (indexados por URL) para no recalcularlos en cada corrida.

**Similitud:**

- Calcula la matriz coseno N×N (N≈104).
- Exporta todos los pares con similitud ≥ 0.40 y los **top-10 vecinos** de cada persona.
- Marca `coautores: true/false` y `first_year` si son coautores. Así el cliente filtra por umbral y por año sin recalcular nada.

**Opcional (recomendado): puntaje combinado de predicción de enlaces**

- `score = 0.7·similitud + 0.3·AdamicAdar_normalizado`, con Adamic-Adar calculado sobre la red de coautoría.
- Expórtalo junto a la similitud y deja elegir en la UI si se ordena por "similitud" o por "puntaje combinado".

**Validación temporal (para el README y la presentación):**

1. Calcula las sugerencias con datos hasta 2022.
2. Mide qué fracción del top-K publicó junta entre 2023 y 2026 (precision@K).
3. Compara con una línea base aleatoria.

Reporta los números.

### 5.4 Métricas de red (`04_metricas.py`, con `networkx` + `scikit-learn`)

Para **cada año Y** del rango (por ejemplo, 2012–2026), sobre el grafo acumulado de coautorías con `first_year ≤ Y` y peso = publicaciones compartidas hasta Y:

- **`degree`**: número de coautores UTEC.
- **`wdeg`**: grado ponderado.
- **`betweenness`**: `nx.betweenness_centrality(G, normalized=True)`. **Decide y documenta** una de dos opciones:
  - no ponderado (más interpretable), o
  - con `weight` como distancia = `1/w`.

  Recomendación: no ponderado para el anillo, y el ponderado guardado como dato extra.
- **`cross_frac`**: fracción del peso de coautoría que va a otros departamentos (alimenta el layout, ver §7.2).
- **`cross_degree`**: número de coautores de otros departamentos.
- **Comunidades:** `nx.community.louvain_communities(G, weight="w", seed=42)`. Se cuentan solo las de 3 o más miembros; el resto queda como `-1` ("sin comunidad").
  - Para que **los colores y etiquetas sean estables entre años**, empareja las comunidades del año Y con las de Y−1 por máxima similitud de Jaccard.
  - Numera C1, C2… por tamaño en 2026.
- **Globales por año:** modularidad Q, NMI y ARI (`sklearn.metrics`) entre comunidad y departamento (solo nodos con comunidad), y porcentaje de aristas entre departamentos.
- **Pureza por comunidad:** porcentaje del departamento dominante y composición por departamento.

**Verificación obligatoria:** un script o test (`pipeline/tests/test_metricas.py`) que recalcule, para 2026, el grado, el betweenness y la modularidad con networkx desde `edges.json` y compare con lo exportado. La rúbrica evalúa "Technical Accuracy".

### 5.5 Exportación (`05_exportar.py`) → `utecviz/static/data/`

- **`nodes.json`** (y **`nodes.csv`** para la entrega): `id`, `nombre`, `iniciales`, `departamento`, `departamentos[]`, `grado_academico`, `citas`, `indice_h`, `renacyt`, `orcid`, `scholar`, `scopus`, `url_perfil`, `foto` (ruta a la miniatura), `temas_top[]`, `pubs_total`, `pubs_por_anio_activo`, `pubs_fraccional`, `primer_anio`, `tiene_vector`.
- **`edges.json`** (y **`edges.csv`**): `source`, `target`, `w`, `w_frac`, `first_year`, `w_by_year{}`, `cross`, `n_pubs`, `pubs[]` (máximo 5 títulos y URLs para la ficha).
- **`similarity.json`**: `[{source, target, sim, score_combinado, coautores, first_year}]` con sim ≥ 0.40.
- **`metrics_by_year.json`**: `{ "2012": { "nodes": {id: {degree, wdeg, bc, cross_frac, cross_degree, comm}}, "global": {Q, NMI, ARI, pct_cross, n_comm}, "communities": [{id, size, pureza, composicion}] }, … }`
- **`layout.json`** (opcional, ver §8): posiciones precalculadas por modo.
- **Fotos:** miniaturas cuadradas de 96×96 px, recortadas al centro, en **WebP** (con JPEG de respaldo). Van a `static/img/fotos/{id}.webp`. Detecta la foto por defecto del sitio (sin foto real), por ejemplo por hash repetido, y usa iniciales en su lugar.

---

## 6. Optimización: qué precalcular y qué hacer en el cliente

| Cálculo | Dónde | Razón |
|---|---|---|
| Embeddings y matriz de similitud | **Offline** | Costoso y determinista; requiere ML. |
| Betweenness, Louvain, NMI, Q por año | **Offline** (`metrics_by_year.json`) | Louvain no es determinista en el navegador y el betweenness es O(VE). Precalcular evita saltos durante la animación y garantiza la exactitud de las métricas. |
| Emparejamiento de comunidades entre años | **Offline** | Mantiene colores y etiquetas estables. |
| Aristas activas por año y su peso acumulado | **Cliente** (filtrar `edges` con `first_year ≤ Y`, sumar `w_by_year`) | Trivial con ~100 nodos; evita duplicar datos. |
| Filtro de similitud por umbral y por "solo entre departamentos" | **Cliente** | Es un filtro sobre una lista pequeña ya exportada. |
| Simulación de fuerzas | **Cliente**, con arranque en caliente | Ver §8. |
| Miniaturas de fotos | **Offline** | Las 104 fotos pesan poco tras el redimensionado; se precargan como `<pattern>` SVG. |

Más reglas:

- **Flask** sirve `static/data/*.json` con `Cache-Control` y ETag. No hay cómputo por request.
- Separa las dependencias: `requirements.txt` (solo la app: `flask`) y `requirements-pipeline.txt` (`pandas`, `networkx`, `scikit-learn`, `sentence-transformers`, `pillow`, `numpy`). La app debe arrancar sin las dependencias de ML.
- **D3 v7** con versión fija (por ejemplo, `d3@7.9.0`), **servido localmente** desde `static/vendor/` para que funcione sin internet durante la presentación.
- Usa SVG; ~104 nodos y unas pocas centenas de aristas no requieren canvas.
- Interrumpe las transiciones (`selection.interrupt()`) antes de lanzar otras.
- Durante el ▶ de la animación, no reconstruyas el DOM: usa *data join* con claves estables (`id`, `source-target`).

---

## 7. La visualización

Hay **una sola red**. Los botones **nunca cambian el grafo**: solo cambian posiciones (con transición animada) u opacidades y capas superpuestas.

### 7.1 Codificaciones (fijas)

- **Nodo = docente.** Relleno con su **foto** (`<pattern>` o `<clipPath>` circular); si no hay foto, se muestran sus iniciales.
- **Tamaño del nodo** = `wdeg` del año seleccionado, con escala `d3.scaleSqrt` cuyo **dominio está fijo al máximo de 2026**, rango de unos 6–28 px. No cambia con ningún botón.
- **Color = departamento principal**, como un borde de color de 3 px alrededor de la foto (y como relleno cuando no hay foto).
- **Anillo de puente:** un segundo círculo exterior oscuro, separado del borde de color por un pequeño hueco.
  - Grosor proporcional al betweenness, entre 1.5 y 6 px.
  - Solo se dibuja si `bc ≥ 12%` del máximo del año.
  - Botón **"Anillo de puentes"** (encendido por defecto) para mostrarlo u ocultarlo. Al apagarlo se ocultan también las etiquetas de los 5 mayores puentes y la fila del anillo en "Cómo leer la red". El nodo seleccionado conserva un anillo fino de selección.
- **Aristas de coautoría:** grosor ∝ √w. Si son **entre departamentos**, se dibujan en tinta oscura; si son internas, en gris claro.
- **Aristas de colaboración potencial** (solo con el botón activo): punteadas y de un color de acento (rojo), más gruesas si son entre departamentos y con opacidad ∝ similitud.
- **Etiquetas de texto:** solo para los 5 mayores puentes, para la selección y su vecindario, y para el top 3 de pares potenciales. Usan un halo del color de fondo para que se lean sobre las aristas.

### 7.2 Layout (clave para T2)

Es un ***force layout* agrupado por departamento** (`d3.forceSimulation`). La idea es que los puentes queden *entre* zonas sin necesidad de encerrarlos:

- **Anclas:** cada departamento tiene un punto ancla sobre una elipse alrededor del centro (radio ≈ 34% del ancho y del alto). Su nombre se escribe fuera de la elipse, a unas 1.3× la distancia del ancla.
- **Atracción al ancla:** `forceX`/`forceY` hacia el ancla de su departamento, con fuerza **`0.26·(1 − 0.85·cross_frac)`**. Quien colabora casi solo dentro de su departamento se queda en su zona; quien colabora mucho fuera queda "suelto" y lo arrastran sus coautores al espacio entre departamentos. Los aislados usan una fuerza de 0.2.
- **Enlaces:** `forceLink` con distancia ≈ 55. La fuerza es 0.35 si la arista es interna y 0.07 si es entre departamentos (para no colapsar las zonas).
- **Repulsión y colisión:** `forceManyBody` con fuerza ≈ −60 y `distanceMax` ≈ 180; `forceCollide(r + 3)` con 2 iteraciones.
- **Modo "Comunidad":** las anclas pasan a ser las comunidades (sobre un círculo), con fuerza de 0.2. Los enlaces dentro de una comunidad tiran con 0.35 y el resto con 0.01. Los nodos sin comunidad van a un anillo exterior junto a su departamento.
  - Se dibujan las comunidades como **manchas suaves** (casco convexo con trazo grueso redondeado y relleno muy tenue), etiquetadas C1, C2…
  - Las etiquetas de departamento se ocultan.
  - El color sigue siendo el departamento: así una mancha multicolor indica una comunidad interdisciplinaria.
- **Transiciones:** al cambiar de modo, de año o de tamaño de ventana, se recalculan las fuerzas y se recalienta la simulación (`alpha` entre 0.35 y 0.6).

### 7.3 Colores

- **Paleta categórica en orden fijo**, asignada por departamento de forma estable (la misma persona tiene siempre el mismo color). Debe ser apta para daltonismo; puedes partir de: `#2a78d6, #eb6834, #1baf7a, #eda100, #e87ba4, #008300, #6250d6, #e34948`. Valídala contra el fondo final.
- **Si hay más de 8 departamentos**, no generes más tonos. Opciones:
  - colorear por **facultad** y usar el departamento como ancla y etiqueta, o
  - agrupar los departamentos pequeños en "Otros" (gris).

  Documenta la decisión.
- Soporta **modo oscuro** con variables CSS, tanto por `prefers-color-scheme` como con un toggle manual.
- El texto nunca usa el color de una serie; la identidad nunca depende solo del color: la leyenda siempre está presente y hay etiquetas y tooltip.

### 7.4 Interacciones (obligatorias según la rúbrica)

Siguen el mantra de Shneiderman: **vista general → zoom y filtro → detalles a pedido**.

- **Hover sobre un nodo** (`mouseenter`/`mouseleave`): tooltip con nombre, departamento, grado ponderado, número de coautores (y cuántos de otros departamentos), betweenness (indicando si está en el top 5), comunidad e índice h. Además se resaltan sus aristas y se atenúa el resto.
- **Clic en un nodo:** fija la **red personal** (el nodo y sus vecinos; el resto al 15% de opacidad) y abre la **ficha** en el panel. La ficha incluye:
  - foto, departamento y grado académico;
  - grado ponderado, betweenness, comunidad, número de coautores (y de otros departamentos) e índice h;
  - temas principales;
  - coautores con número de publicaciones compartidas (resaltando los de otros departamentos), que se pueden expandir para ver los títulos;
  - "más similares sin coautoría" (top 3 por similitud);
  - enlaces a ORCID, Scholar y el perfil CRIS.

  Un clic en el fondo o en "Cerrar" la libera.
- **Leyenda de departamentos clicable:** oculta o atenúa departamentos.
- **Buscador por nombre** con autocompletado: centra y selecciona al docente.
- **Zoom y pan** (`d3.zoom`) y **arrastre** de nodos (`d3.drag`).
- **Slider de año y botón ▶ Animar:** de 2012 a 2026, unos 900 ms por año. Muestra el año en grande como marca de agua. Las métricas, rankings y paneles se actualizan con `metrics_by_year`.
- **Agrupar por: Departamento | Comunidad.**
- **Anillo de puentes** (toggle).
- **Colaboraciones potenciales** (toggle). Al activarlo:
  - las coautorías bajan al ~7% de opacidad y se dibujan las punteadas;
  - aparecen el **slider de umbral** (0.50–0.95, por defecto 0.70) y el check **"Solo entre departamentos"** (activo por defecto);
  - en el panel aparece el **top 10 de parejas**; al pasar el mouse por una se resalta en la red y al hacer clic se selecciona.

  En la animación, los pares que ya son coautores en el año Y no se muestran como potenciales.

### 7.5 Panel lateral

Su contenido se adapta al estado:

1. Ficha del docente (si hay uno seleccionado).
2. Pares potenciales (si el toggle está activo).
3. Comunidades (en modo comunidad): NMI, Q y una tabla con la composición y la pureza de cada comunidad.
4. **Ranking del año** con selector **Prolíficos | Puentes** (top 8, con barras), y el porcentaje de coautorías entre departamentos.
5. **"Cómo leer la red"**: leyenda visual de cada codificación (tamaño, anillo, línea oscura y clara, punteada) y una frase sobre el significado de la posición en el modo actual.

En pantallas estrechas (menos de unos 860 px), el panel pasa debajo de la red.

---

## 8. Rendimiento del layout

- **Arranque en caliente:** antes de mostrar nada, ejecuta `simulation.tick(300)` de forma síncrona con la simulación detenida y luego renderiza. Así la red no aparece "explotando".
- **Opcional:** precalcula offline posiciones finales (por ejemplo, con un script Node que use exactamente la misma definición de fuerzas) para los modos departamento y comunidad en 2026, guardadas en `layout.json`. El cliente parte de esas posiciones con un `alpha` bajo. Esto da un layout reproducible entre recargas, útil para la presentación. Si lo haces, normaliza las coordenadas a [0,1] y escálalas al tamaño del contenedor.
- Recalienta solo cuando cambian el modo, el año o el tamaño. Los toggles de opacidad (anillos, potenciales, filtros) **no** tocan la simulación.

---

## 9. Página web: "UtecVis by Batimix"

- **Nombre visible y `<title>`:** **UtecVis by Batimix**.
- **Estilo de página web completa**, no un dashboard pelado:
  1. **Encabezado/hero:** título, subtítulo de una línea ("Quién colabora con quién en la investigación de UTEC") y tres o cuatro cifras clave (docentes, publicaciones, porcentaje de coautorías entre departamentos, número de comunidades).
  2. **La visualización** a pantalla casi completa, con los controles en una sola fila encima.
  3. **Las 4 preguntas:** tarjetas breves que explican cada tarea y, al hacer clic, **configuran la vista** (por ejemplo, "¿Quiénes son puentes?" activa los anillos y desplaza hasta la red). Sigue siendo una sola visualización; las tarjetas solo la controlan.
  4. **Hallazgos:** 3–5 *insights* redactados a partir de los datos reales (por ejemplo, top puentes, NMI, la pareja potencial más fuerte entre departamentos).
  5. **Metodología:** fuente de los datos, fecha del scraping, cómo se define una arista, qué modelo de embeddings se usó, cómo se calculan las métricas y sus limitaciones (hiperautoría, perfiles sin publicaciones, el peso de la huella digital como medida relativa).
  6. **Pie de página:** "UtecVis by Batimix · DS5343 Visualización de Datos · UTEC 2026-2".
- **Referencia estética:** está en **`utecviz/referencia_estetica/`**. Es **ÚNICAMENTE una referencia ESTÉTICA**: de ahí tomas tipografía, paleta de fondo y superficies, espaciado, estilo de botones y tarjetas, y tono visual. **No copies su contenido, su estructura de información ni sus funcionalidades**, y no dejes que contradiga las codificaciones definidas aquí (por ejemplo, la paleta categórica de departamentos manda sobre los colores decorativos de la referencia).
- **Accesibilidad:**
  - contraste AA en el texto;
  - foco visible en los controles;
  - controles operables con teclado (Tab, Enter y Espacio en los toggles; flechas en el slider);
  - `aria-pressed` en los toggles;
  - un enlace "Ver datos como tabla" que muestre los rankings en una tabla HTML.

---

## 10. Estructura del proyecto

```
utecviz/
  app.py                      # Flask: index + estáticos con caché
  templates/index.html
  static/
    css/style.css
    js/main.js                # orquestación, estado, controles
    js/network.js             # render D3 y layout
    js/panel.js               # panel lateral, ficha y rankings
    vendor/d3.v7.9.0.min.js
    data/nodes.json  edges.json  similarity.json  metrics_by_year.json  [layout.json]
    img/fotos/*.webp
  data/
    raw/                      # ZIPs descomprimidos del scraping
    manual/departamentos_override.csv
    processed/                # intermedios, embeddings cacheados, reporte_calidad.md
  entrega/nodes.csv  entrega/edges.csv   # copias planas para la entrega
  pipeline/01_…05_*.py  tests/
  referencia_estetica/        # (provista; solo estética)
  requirements.txt  requirements-pipeline.txt
  README.md
```

- **Estado centralizado** en un solo objeto (`{year, group, rings, potential, threshold, crossOnly, selected, hiddenDepts, rankMode}`). Cada control modifica el estado y llama a `render(state)`.
- Usa un `Makefile` o `run_pipeline.sh` que ejecute los 5 scripts en orden.
- **README** con: cómo correr el pipeline y la app (`flask run`), las decisiones de diseño (por qué cada codificación), las métricas y sus definiciones, los resultados de la validación temporal de T4 y las limitaciones.

---

## 11. Checklist de aceptación

- [ ] Solo D3 para visualizar; la app Flask arranca con `pip install -r requirements.txt && flask run`.
- [ ] `nodes.csv`/`edges.csv` (y los JSON) incluidos y coherentes entre sí.
- [ ] 104 nodos; cada persona sin coautores aparece aislada; las 2.976 relaciones persona–publicación cruzan sin pérdidas (o están reportadas).
- [ ] Las métricas exportadas coinciden con networkx (test pasando).
- [ ] El tamaño de los nodos no cambia al usar los botones; el color siempre es el departamento.
- [ ] Los puentes se reconocen por posición (entre zonas) y por el anillo, que se puede encender y apagar.
- [ ] El botón de comunidad reordena con animación; el panel muestra NMI, Q y pureza.
- [ ] El botón de potenciales atenúa las coautorías, muestra las punteadas y el slider de umbral funciona.
- [ ] La animación 2012→2026 funciona, sin saltos de color en las comunidades.
- [ ] Hay hover, clic, leyenda, buscador, zoom y arrastre.
- [ ] La página "UtecVis by Batimix" sigue la estética de `referencia_estetica/` sin copiar su contenido.
- [ ] Funciona sin internet (D3 local), en modo claro y oscuro, y en pantallas estrechas.