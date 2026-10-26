# Reporte de calidad de datos

## Departamentos

- Unidades distintas tras normalizar: **16**
- Correcciones manuales aplicadas: 0

Personas sin `Departamento de …` en sus cargos (se usó Facultad / Escuela / Centro / Instituto, o quedan como *Sin departamento*). Para corregir, añadir filas a `data/manual/departamentos_override.csv`:

| id | asignado | tipo | cargos |
|---|---|---|---|
| jesús-edwin-bellido-angulo | Facultad de Computación | Facultad | Decano, Facultad de Computación · Grupo de Investigación en Inteligencia Artificial (GINIA) · Universidad de Ingeniería y Tecnología - UTEC |
| rayna-alexandra-benzeev | Instituto de Investigación para la Sostenibilidad de la Amazonía - ASRI | Instituto | Investigador Asociado Senior, Instituto de Investigación para la Sostenibilidad de la Amazonía - ASRI · Investigador Asociado Senior, Universidad de Ingeniería y Tecnología - UTEC |
| aoife-bennett | Instituto de Investigación para la Sostenibilidad de la Amazonía - ASRI | Instituto | Director, Instituto de Investigación para la Sostenibilidad de la Amazonía - ASRI · Investigador Asociado Senior, Universidad de Ingeniería y Tecnología - UTEC |
| ruth-canahuire-cabello | Centro de Investigación en Bioingeniería - BIO | Centro | Directora General Académica, Universidad de Ingeniería y Tecnología - UTEC · Investigador, Grupo de Investigación en Robótica, Inteligencia Artificial y Control Avanzado (RIC) · Investigador, Centro de Investigación en Bioingeniería - BIO |
| jose-gerardo-deustua-rossel | Sin departamento | — | Director, Dirección General de Innovación e Investigación · Universidad de Ingeniería y Tecnología - UTEC |
| bryam-orihuela-pinto | Instituto de Investigación para la Sostenibilidad de la Amazonía - ASRI | Instituto | Universidad de Ingeniería y Tecnología - UTEC · Investigador Asociado, Instituto de Investigación para la Sostenibilidad de la Amazonía - ASRI |
| enrique-stiglich-labarthe | Sin departamento | — | Rector, Universidad de Ingeniería y Tecnología - UTEC |
| eunice-villicaña-ortiz | Facultad de Ingeniería | Facultad | Decano, Facultad de Ingeniería · Investigador, Grupo de investigación en energía y minas · Universidad de Ingeniería y Tecnología - UTEC |
| akira-armando-wong-sato | Instituto de Investigación para la Sostenibilidad de la Amazonía - ASRI | Instituto | Investigador, Instituto de Investigación para la Sostenibilidad de la Amazonía - ASRI · Universidad de Ingeniería y Tecnología - UTEC |

| unidad | personas |
|---|---|
| Ciencia de Computación y de Datos | 14 |
| Bioingeniería e Ingeniería Química | 13 |
| Ciencias | 12 |
| Ingeniería Electrónica y Mecatrónica | 11 |
| Ingeniería Civil y Ambiental | 11 |
| Ingeniería Mecánica y de la Energía | 10 |
| Humanidades, Artes y Ciencias Sociales | 8 |
| Ingeniería Industrial y Gestión de la Ingeniería | 8 |
| Instituto de Investigación para la Sostenibilidad de la Amazonía - ASRI | 4 |
| Sistemas y Seguridad de la Información | 4 |
| Negocios Digitales | 2 |
| Sin departamento | 2 |
| Física | 2 |
| Facultad de Computación | 1 |
| Centro de Investigación en Bioingeniería - BIO | 1 |
| Facultad de Ingeniería | 1 |

## Publicaciones y coautoría

- Filas persona–publicación (`publicacion_investigador.csv`): 2976; cruzan por nombre exacto: 2976 (100.0%); sin cruce: 0
- Publicaciones únicas (por URL): 2479; sin año: 0
- Hiperautoría (> 50 autores o firma colectiva): 1134 (609 con firma colectiva; para ellas n_eff = 588, mediana de las hiperautorías con lista)
- Publicaciones con autores ocultos tras 'Mostrar N otros' (conteo corregido +1): 545
- `EXCLUIR_HIPERAUTORIA = True`. Pares de coautores cuya única coautoría es hiperautoría (no generan arista): 1 → diego-alejandro-milanés-carreño – evgenii-vladimirovich-shmanin (433 pubs)
- Aristas de coautoría: 35 (17 entre departamentos)
- Personas con publicaciones: 80 de 104
