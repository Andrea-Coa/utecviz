# UtecVis by Batimix

**Quién colabora con quién en la investigación de UTEC.** Una sola visualización de red (D3 v7) de los 104 docentes e investigadores con perfil en el portal de investigación de UTEC (`cris.utec.edu.pe`), servida con Flask.

- Nodo = docente (con su foto). Arista = al menos una publicación compartida.
- Cinco tareas (T1–T5) y una animación temporal 2012→2026.
- Todo el cálculo pesado (embeddings, métricas, comunidades) se hace **offline** en un pipeline de Python. Lo único que se calcula en vivo es el vector del tema que escribe el usuario en T5.

## Cómo correrlo

### App

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt   # Flask + sentence-transformers y torch (para T5)
flask run                         # http://127.0.0.1:5000  (en macOS, si el 5000 da 403 por AirPlay: flask run --port 5050)
```

Los datos ya calculados están en `static/data/`. D3 y la tipografía se sirven en local (`static/vendor/`, `static/fonts/`).

**T5 necesita internet la primera vez**: al arrancar, la app descarga el modelo `intfloat/multilingual-e5-base` (~1 GB, queda en la caché de Hugging Face) y lo carga en segundo plano (1–2 min; luego cada búsqueda tarda ~50 ms). Mientras tanto el panel dice «Buscando…». Sin `sentence-transformers`/`torch` instalados, T1–T4 funcionan igual y T5 muestra un aviso.

### Publicar en GitHub Pages (con T5 en Hugging Face Spaces)

GitHub Pages solo sirve archivos: T1–T4 funcionan tal cual, pero T5 necesita ejecutar el modelo. Por eso la página va en Pages y la API de T5 en un **Space de Hugging Face** (gratis, SDK Gradio: una app de Gradio es un servidor FastAPI, al que `deploy/space/app.py` le agrega la ruta `/api/tema`). No hay llaves ni secretos: el Space corre `tema.py` y descarga el modelo al arrancar. Tiene CORS limitado a `andrea-coa.github.io`, un máximo de 30 búsquedas por minuto por IP y temas de hasta 300 caracteres.

```bash
python deploy/precalcular_t5.py                 # respaldo: static/data/tema_precalc.json
python deploy/preparar_space.py                 # dist/space/: carpeta para subir al Space
# (subir dist/space/ al Space de Hugging Face, SDK Gradio)
python deploy/build_pages.py --api https://<usuario>-<space>.hf.space/api/tema   # docs/
```

Pages se activa en *Settings → Pages → Deploy from a branch → `main` / `/docs`*. Si el Space está dormido (sin uso por ~48 h) o no responde en 5 s, la página muestra el **resultado precalculado** más cercano: hay 26 habilidades, 325 pares de habilidades y 24 temas de ejemplo, y en el texto libre se detectan las habilidades por palabras clave. Ese resultado se marca como «aproximado» y se reemplaza solo cuando responde el Space. Además, al abrir la página se le envía un pedido para que despierte.

### Pipeline (opcional: regenera `static/data/`)

```bash
pip install -r requirements-pipeline.txt      # pandas, networkx, scikit-learn, sentence-transformers, torch, pillow
./run_pipeline.sh                              # 01 → 05 y el test de métricas
```

| Script | Qué hace |
|---|---|
| `pipeline/01_limpieza.py` | Personas: id (slug del perfil), departamento, grado académico, citas/índice h, RENACYT, temas |
| `pipeline/02_coautoria.py` | Publicaciones únicas, nº de autores, hiperautoría, aristas con pesos por año, productividad |
| `pipeline/03_embeddings.py` | Embeddings de publicaciones y perfiles, vector por persona, similitud, Adamic-Adar, validación temporal |
| `pipeline/04_metricas.py` | Por año (2012–2026): grado, grado ponderado, betweenness, comunidades Louvain estables, Q, NMI, ARI, pureza |
| `pipeline/05_exportar.py` | `nodes/edges/similarity/metrics_by_year/departamentos/resumen.json`, CSV de entrega y miniaturas de fotos |
| `pipeline/tests/test_metricas.py` | Recalcula con networkx, desde `edges.json`, el grado, el betweenness y la modularidad de 2026 y los compara con lo exportado |

Los embeddings se cachean en `data/processed/emb_pubs.npy` (por URL) y `emb_perfiles.npy`; una segunda corrida no los recalcula. Los parámetros están en `pipeline/config.py`.

## Estructura

```
utecviz/
  app.py  tema.py (T5)  templates/index.html  requirements.txt  requirements-pipeline.txt  run_pipeline.sh
  static/css/style.css  static/js/{main,network,panel}.js  static/vendor/d3.v7.9.0.min.js  static/fonts/
  static/data/   nodes.json edges.json similarity.json metrics_by_year.json departamentos.json resumen.json (+ nodes.csv, edges.csv)
  static/img/fotos/{id}.webp|.jpg     miniaturas 96×96
  entrega/       nodes.csv edges.csv reporte_calidad.md      copias planas para la entrega
  pipeline/      01…05 + config.py + tests/
  data/manual/departamentos_override.csv    correcciones manuales de departamento (vacío)
  data/processed/                            intermedios, embeddings cacheados, reporte_calidad.md
  utec_perfiles/ (+ utec_publicaciones_detalle/)   datos crudos del scraping, tal cual
```

Los datos crudos se dejaron en `utec_perfiles/` (su ubicación original) en lugar de copiarlos a `data/raw/`.

## Público y tareas

**Público principal:** la Dirección de Investigación y los jefes de departamento (ver la estructura de colaboración, a las personas clave y los silos, y encontrar oportunidades interdisciplinarias). **Secundario:** docentes que buscan coautores fuera de su departamento y estudiantes de posgrado que buscan asesor.

| # | Pregunta | Métrica | Codificación |
|---|---|---|---|
| T1 | ¿Quiénes colaboran más dentro de UTEC? | Grado ponderado (publicaciones compartidas con otros docentes UTEC) | Tamaño del nodo (escala √, dominio fijo al máximo de 2026) + ranking «Prolíficos» |
| T1b | ¿Quiénes tienen más impacto? | Índice h (Scopus, del perfil) | Botón «Tamaño: Calidad (h)»: el radio pasa a escala √ del índice h (sin dato = mínimo); «Contribución» (por defecto) vuelve al grado ponderado |
| T2 | ¿Quiénes son puentes entre departamentos? | Betweenness (no ponderado, normalizado) + fracción de coautoría fuera del departamento | Anillo oscuro (grosor ∝ betweenness, desde el 12 % del máximo del año) + posición entre zonas + aristas entre departamentos en tinta oscura + ranking «Puentes» |
| T3 | ¿Las comunidades coinciden con los departamentos? | Louvain, modularidad Q, NMI y ARI comunidad↔departamento, pureza | Botón «Agrupar por: Comunidad»: los nodos se reordenan con transición; manchas C1…Cn; el color sigue siendo el departamento |
| T4 | ¿Qué colaboraciones nuevas son probables? | Similitud coseno de embeddings en pares sin coautoría (opcional: 0,7·sim + 0,3·Adamic-Adar) | Botón «Colaboraciones potenciales»: coautorías al 7 %, punteadas rojas, umbral y filtro «solo entre departamentos», top 10 en el panel |
| T5 | Dado un tema, ¿quiénes podrían formar el equipo? | Similitud coseno entre el tema (e5, prefijo `query:`) y las publicaciones y perfiles de cada docente; camino más corto entre candidatos | Campo «Tema» (texto libre o una de 26 habilidades): el tema se descompone en facetas; una estrella con etiqueta por faceta junto a sus expertos y una estrella del tema entre ellas; líneas de puntos (grosor ∝ cercanía); solo se ven el equipo, sus coautorías y los puentes que los unen |
| ▶ | ¿Cómo evolucionó la red? | Todas las métricas, precalculadas por año 2012–2026 | Slider de año y botón ▶ (900 ms por año), año en marca de agua |

## Decisiones de diseño

- **La red es la protagonista.** Ocupa toda la pantalla (salvo los controles). La marca, las cifras y el panel de detalle (ranking, ficha, equipo) van en una barra lateral que se puede plegar (‹). «Cómo leer la red» vive en la leyenda, dentro de la red y abajo a la izquierda: es lo primero que se lee sin tapar el grafo. Muestra solo las codificaciones activas (el anillo si está encendido, la línea roja con T4, la estrella con T5) y se puede plegar.
- **Una sola red; los botones nunca cambian el grafo.** Solo mueven nodos (con la simulación de fuerzas) o cambian opacidades y capas. Así el lector no pierde el mapa mental entre tareas.
- **Vista jerárquica** («Agrupar por: Jerárquico»): un complemento ordenado de la vista por departamento, no un reemplazo. Usa la jerarquía UTEC → departamento → persona en disposición radial con *hierarchical edge bundling* (Holten, 2006), con `d3.curveBundle` y `d3.arc`:
  - Cada departamento ocupa un sector, en el mismo orden que sus zonas.
  - En el anillo interior van quienes tienen coautores UTEC en el año elegido, ordenados por comunidad y grado ponderado; en el exterior, quienes no tienen.
  - Las coautorías pasan por el centro de su departamento y, si cruzan departamentos, por el centro del círculo, de modo que forman haces.
  - Con la animación, las personas pasan del anillo exterior al interior al conseguir su primer coautor.
  - Los nodos conservan su tamaño. Cuando un sector tiene muchos nodos grandes (Bioingeniería, Mecánica), estos se comprimen y pueden encimarse un poco.
- **Nodo = foto** (pide el enunciado) recortada en círculo, con un **borde de color = departamento**. Sin foto real (2 *placeholders* del portal), se muestran las iniciales sobre el color.
- **Tamaño fijo por año** (no por botón): el dominio de la escala es el máximo de 2026, así que durante la animación los nodos crecen de verdad.
- **Puentes por dos canales**: el anillo (métrica exacta) y la posición. La atracción al ancla del departamento es `0,26·(1 − 0,85·cross_frac)`, de modo que quien colabora fuera queda «suelto» y sus coautores lo llevan al espacio entre zonas.
- **Color**: paleta categórica validada para daltonismo (comprobada con un validador de ΔE en OKLab contra el fondo claro y el oscuro). Hay 16 unidades, pero solo 7 tonos utilizables (el rojo queda reservado para «potencial»). Por eso los 7 departamentos con más personas con publicaciones tienen color y el resto comparte el gris «Otros». Entre los 7 tonos no todos los pares se distinguen con daltonismo, así que la identidad nunca depende solo del color: cada departamento tiene su **zona** y su **etiqueta**, y además están la leyenda, el tooltip y la tabla.
- **Zonas**: las unidades de una sola persona (dos facultades y un centro) y las 2 personas sin unidad (Rector, Dirección de Innovación) comparten la zona «Dirección, facultades y centros». El Instituto de la Amazonía (ASRI, 4 personas) tiene zona propia.
- **Texto nunca en color de serie**; las etiquetas llevan halo del color de fondo. Se rotulan solo los 5 mayores puentes, la selección y su vecindario, y el top 3 de pares potenciales.
- **Estética**: inspirada en `referencia_estetica/` (portal de diseño web de 2004): trama de fondo, marco blanco, barras de título granate con tipografía pixelada (Silkscreen, servida en local), botones con borde. Solo se toma lo visual; la información y las funciones son propias.
- **Accesibilidad**: contraste AA en el texto, foco visible, toggles con `aria-pressed`, controles por teclado (Tab/Enter/Espacio; flechas en los sliders), Escape cierra la ficha, tabla de datos alternativa y modo oscuro (sistema o botón).

## Métricas (definiciones)

- **Arista**: dos docentes del portal firman juntos al menos una publicación. `w` = publicaciones compartidas; `w_frac` = Σ 1/(n_autores − 1); `w_by_year` = conteo por año; `cross` = departamentos principales distintos.
- **Red del año Y**: aristas con `first_year ≤ Y` y peso acumulado hasta Y (calculado en el cliente a partir de `w_by_year`; las métricas vienen precalculadas).
- **degree / wdeg**: nº de coautores UTEC / publicaciones compartidas.
- **betweenness**: `nx.betweenness_centrality(G, normalized=True)` sin pesos (más interpretable: «cuántos caminos cortos pasan por ti»). La versión con distancia 1/w se exporta como `bc_w`.
- **cross_frac / cross_degree**: fracción del peso de coautoría y nº de coautores en otros departamentos.
- **Comunidades**: `louvain_communities(G, weight="w", seed=42)`. Solo cuentan las de 3 o más personas (el resto, −1). Las etiquetas se fijan por tamaño en 2026 (C1, C2…) y hacia atrás cada año se empareja con el siguiente por máxima similitud de Jaccard, de modo que los colores y etiquetas no saltan durante la animación.
- **Globales**: Q (modularidad de la partición de Louvain), NMI y ARI comunidad↔departamento (solo nodos con comunidad), % de aristas entre departamentos.
- **Pureza**: % del departamento dominante en cada comunidad.

## Hiperautoría

1134 de las 2479 publicaciones tienen más de 50 autores o solo la firma de un consorcio (LHCb, BaBar). En 609 de ellas, el investigador UTEC no aparece por nombre en la lista de autores. El nº de autores se corrige por un artefacto del scraping: en listas largas el texto termina en «Mostrar N otros» y los N autores ocultos quedan pegados al último visible.

`EXCLUIR_HIPERAUTORIA` (en `pipeline/config.py`) vale **`True`** en esta versión. Las instrucciones proponían `False` por defecto; se cambió tras medir el efecto:

| | `False` | `True` (usado) |
|---|---|---|
| Aristas | 36 | 35 |
| Arista más pesada | Milanés–Shmanin, w = 433 (todas LHCb) | 6 publicaciones |
| Efecto en T1 | los otros 102 nodos quedan entre 8 y 11 px de radio (frente a 30 px de esos dos): el tamaño deja de comunicar | rango completo de tamaños |

Solo cambia un par: Diego Milanés y Evgenii Shmanin, que comparten 433 artículos de LHCb con cientos de firmantes. Con `True` no forman arista, pero la ficha de cada uno indica esas publicaciones compartidas. Para volver al comportamiento original: `EXCLUIR_HIPERAUTORIA = False` y `./run_pipeline.sh`.

## Colaboraciones potenciales (T4)

**Qué tipo de predicción es.** Predecir colaboraciones nuevas es *link prediction* (una arista nueva entre nodos que ya existen), no *node prediction*. Se usan dos señales: una **basada en contenido** (similitud coseno de embeddings: quienes investigan lo mismo) y una **estructural** (Adamic-Adar: coautores en común con pocos contactos). No es un modelo entrenado: con 14 colaboraciones nuevas en 2023–2026 no hay ejemplos suficientes para aprender uno. Por eso se valida como un problema de predicción real, con un corte temporal (ver abajo). T5, en cambio, no predice: recupera a quién sabe de un tema.

- **Texto de cada publicación**: título + resumen; modelo multilingüe `intfloat/multilingual-e5-base` (prefijo `passage:`, 512 tokens). Se eligió frente a `bge-m3` porque tiene la mitad de parámetros (278 M frente a 568 M): en esta CPU las 2479 publicaciones tardaron unos 40 min, una sola vez gracias a la caché. El corpus mezcla inglés (97 %) y español.
- **Vector de la persona** = 0,75 · promedio ponderado de sus publicaciones + 0,25 · embedding del perfil (perfil profesional + temas de interés + 25 conceptos de la huella), normalizado L2. Peso de cada publicación: `exp(−(2026 − año)/8) · min(1, 10/n_autores)` (recencia y atenuación de equipos grandes). Las 104 personas tienen vector: las 24 sin publicaciones usan solo su perfil.
- **Similitud**: coseno **tras centrar** los vectores (restar la media). Los modelos e5 dan cosenos comprimidos entre 0,7 y 0,9 para casi cualquier par; centrar devuelve un rango interpretable (mediana −0,02, percentil 99 = 0,49, máximo 0,84). Por eso el slider va de **0,40 a 0,80 (0,50 por defecto)** y no de 0,50 a 0,95 como proponían las instrucciones: con 0,70 solo quedaban 3 pares sin coautoría. Se exportan los pares con similitud ≥ 0,40 más los 10 vecinos de cada persona (656 pares).
- **Puntaje combinado** = 0,7 · similitud + 0,3 · Adamic-Adar normalizado (sobre la red de coautoría). La red es tan dispersa que Adamic-Adar casi nunca es positivo para pares sin coautoría, así que ambos rankings prácticamente coinciden.

**Validación temporal.** Se recalcularon vectores y red solo con publicaciones hasta 2022 y se comprobó qué pares sin coautoría en 2022 publicaron juntos en 2023–2026:

| Ranking | Candidatos | Pares nuevos | Base aleatoria | Precisión@10 | Precisión@50 | Precisión@100 | AUC |
|---|---|---|---|---|---|---|---|
| Similitud (todos los pares) | 5335 | 14 | 0,26 % | 10 % (1) | 4 % (2) | 4 % (4) | **0,83** |
| Similitud (solo entre departamentos) | 4881 | 3 | 0,06 % | 0 % | 0 % | 0 % | 0,43 |
| Puntaje combinado (todos) | 5335 | 14 | 0,26 % | 10 % (1) | 4 % (2) | 4 % (4) | 0,83 |

En el conjunto de pares, la similitud ordena bien a quienes después colaboran (AUC 0,83; el top 10 rinde unas 38 veces más que el azar). Entre departamentos distintos solo hubo 3 colaboraciones nuevas y la similitud no las anticipó, así que la vista T4 entre departamentos debe leerse como una **pista de afinidad temática**, no como una predicción.

**Por qué se sugiere cada par.** Cada par exportado lleva su evidencia (`comun`, `pubs_cercanas` en `similarity.json`): los conceptos de la huella de Elsevier que comparten y el par de publicaciones más cercanas (una de cada persona, sin contar las que firman juntos ni las de hiperautoría). Se muestran en el tooltip de la línea roja, en la lista de pares y en el «¿Por qué?» de la ficha.

## Equipo para un tema (T5)

- El tema se convierte en vector con el mismo modelo que T4 (prefijo `query:`, como pide e5) y se compara con los embeddings ya calculados de las publicaciones y los perfiles (`data/processed/emb_*.npy`). Código: `tema.py`, ruta `/api/tema?q=…`.
- **Puntaje de un docente** = 0,75 · media ponderada (0,6 / 0,3 / 0,1) de sus 3 publicaciones más cercanas al tema + 0,25 · similitud con su perfil (mismos pesos que el vector de persona). Quien no tiene publicaciones recibe en el primer término la mediana del grupo; si no, un perfil escrito en español le ganaba por idioma a quien publica sobre el tema. Los pesos 0,6 / 0,3 / 0,1 reemplazaron al promedio plano: con el promedio, Cristian López del Álamo (un paper de EEG) quedaba bajo Aurea Soriano (series multivariadas, sin EEG) incluso en «Señales biomédicas»; con los pesos queda sobre ella y la habilidad Visualización no cambia.
- **Candidatos**: los que superan en 1,5 desviaciones a la media de los 104 (mínimo 3, máximo 8). El % del panel es la cercanía relativa al más cercano.
- **La parte de red**: entre cada par de candidatos se busca el camino más corto (máximo 4 saltos) en la red del año. Se cuentan los pares que ya publicaron juntos, se marcan los **puentes** (quien está en el camino sin ser candidato) y los candidatos **sin camino** hasta otro. Es la respuesta de red: ¿el equipo ya existe o hay que presentarlo?
- Ejemplo: «visualization of brain signals» devuelve a Christian Flores Vega (EEG), Tarrillo y Huamanchahua (Electrónica), y a Soriano, García-Zanabria, Mora y López del Álamo (visualización, Computación). El grupo de Electrónica se une a Wangdo Kim por medio de Eunice Villicaña, pero no existe ningún camino hasta el de Computación: es una colaboración por crear.
- **Facetas (temas compuestos).** Con un solo vector, una frase como «visualization of brain signals» queda en un punto medio y quien es fuerte en una sola parte se diluye. Por eso el tema se descompone en **habilidades de un catálogo de 26** (`HABILIDADES` en `tema.py`): las que destacan (z ≥ 2 entre las 26) frente a la frase completa o frente a cada trozo separado por conectores («with», «for», «con», «para»…). Un trozo solo cuenta si alguna habilidad lo domina claramente (z ≥ 2,8); así «fibras naturales», ambiguo, no agrega Hidrología ni Biomecánica. Máximo 4 facetas. Los 2–3 expertos de cada faceta (z ≥ 2 entre los 104) se suman a la lista.
  - Revisión del catálogo contra los datos: cada habilidad devuelve expertos reconocibles (Visualización: Soriano, García-Zanabria; Elementos finitos: Mantari, Benedetty; Hidrología: Rau, Gutiérrez…), salvo «Grafos y redes», porque casi nadie publica sobre eso en el portal.
  - Ejemplos: «visualization of brain signals» → Señales biomédicas + Visualización, **sin camino corto en la red** entre ambos grupos; «climate change impacts on hydropower energy» → Clima + Energía + Hidrología; «materiales compuestos con fibras naturales» → solo Ensayos de materiales.
  - **En la red**, cada faceta es una estrella pequeña con su nombre, ubicada junto a sus expertos y empujada hacia afuera del lienzo. Las facetas no se distinguen por color, porque el color ya codifica el departamento y la paleta apta para daltonismo está agotada. Se identifican por etiqueta directa y posición, y la distancia entre estrellas muestra cuán separados están hoy esos grupos.
  - **Lista única**, ordenada por cercanía al tema completo (los candidatos del tema más los expertos de cada faceta). Cada persona lleva la etiqueta ★ de las facetas en que destaca: z ≥ 2 en esa habilidad, o z ≥ 1,5 y **al menos un título** que mencione sus términos (`TERMINOS` en `tema.py`; el número en la etiqueta). El embedding sola no basta: en «Señales biomédicas», Cristian López del Álamo (títulos con EEG y EMG) y Aurea Soriano (series multivariadas, sin EEG en ningún título) quedan casi empatados (z 1,80 frente a 1,75). Se usa el título y no el resumen porque en los resúmenes los términos aparecen de pasada.
  - **Panel**: cobertura entre facetas (comparten un experto, coautoría directa, camino de k saltos o sin camino), quién cubre más de una faceta y la lista.
  - Si se elige una habilidad del catálogo, la búsqueda usa su descripción y no el nombre corto.
- **Lo que se descartó**: inferir automáticamente qué habilidad «le falta» a cada docente, por co-ocurrencia de habilidades en las publicaciones. La co-ocurrencia recomienda combinaciones habituales (ML + deep learning), no las que faltan (ML + visualización), y en la validación temporal no superó al azar en el conjunto de pares (AUC 0,53). Por eso la habilidad la elige quien busca.
- Limitación: el corpus está 97 % en inglés y una búsqueda en español favorece un poco a las publicaciones en español. No hay validación cuantitativa: es una herramienta de exploración.

## Resultados principales (2026)

- **Red muy dispersa**: 35 aristas; solo 35 de 104 docentes tienen algún coautor UTEC del portal y 69 aparecen aislados. La primera coautoría interna es de 2013, y las comunidades aparecen desde 2018.
- **Más prolíficos (T1)**: Carmen Flores Barreda (10 publicaciones compartidas), Samuel Charca (10), José Luis Mantari (9) y Ruth Canahuire (9).
- **Puentes (T2)**: José Luis Mantari, Wangdo Kim y Eunice Villicaña tienen el mayor betweenness. El 49 % de los pares de coautores cruzan departamentos.
- **Comunidades (T3)**: 5 comunidades de 3 o más personas, con Q = 0,72 (grupos muy marcados) pero NMI = 0,56 y ARI = 0,30 respecto a los departamentos: coinciden solo en parte. C2 es casi toda de Electrónica y Mecatrónica (86 % de pureza); C1 y C3 mezclan 3 y 4 unidades.
- **Potenciales (T4)**: el par más parecido entre departamentos sin coautoría es Carlos Benedetty (Civil y Ambiental) – Samuel Charca (Mecánica y Energía), con similitud 0,61. Le siguen Ruth Canahuire – Elvis Jara y Walter Barrutia – Emir Vela.

## Calidad de datos y verificación

- 2976 de 2976 relaciones persona–publicación cruzan por nombre exacto del perfil; hay 104 nodos (los aislados se mantienen).
- `entrega/reporte_calidad.md` lista las 9 personas sin `Departamento de …` en sus cargos y la unidad que se les asignó. Las correcciones manuales van en `data/manual/departamentos_override.csv` (`id,departamento,motivo`).
- 2 fotos son el *placeholder* del portal (se detectan por hash): se muestran iniciales.
- `pytest pipeline/tests` recalcula para 2026 el grado, el grado ponderado, el betweenness, la modularidad, la partición de Louvain (misma semilla), el tamaño de las comunidades y `cross` desde los archivos exportados: **5/5 pasan**.

## Limitaciones

- Solo se ven coautorías entre los 104 perfiles del portal: no con el resto de UTEC ni con coautores externos.
- El portal incluye publicaciones anteriores a la llegada de cada persona a UTEC; una coautoría de 2013 puede ser de antes de que ambos trabajaran allí.
- 24 personas no tienen publicaciones en el portal: aparecen aisladas y su vector sale solo del perfil.
- La huella digital de Elsevier es relativa dentro de cada persona (el concepto principal = 100 %); se usa solo como texto, no como peso comparable.
- Con 7 tonos aptos para daltonismo, 6 zonas comparten el gris «Otros»; las distinguen la zona, la etiqueta y la leyenda.
