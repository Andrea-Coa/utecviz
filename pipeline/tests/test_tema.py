"""T5 sin el modelo: un tema sin sentido no debe armar equipo (antes, el más cercano salía siempre al 100 %)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tema  # noqa: E402


@pytest.fixture(scope="module")
def datos():
    return tema._cargar_datos()


@pytest.mark.parametrize("q", ["akjdfnalidbfahdliua", "qwerty", "lorem ipsum dolor", "jfjfjf ksksk", "123456", "?"])
def test_tema_sin_sentido(datos, q):
    desconocidas, total = tema.palabras_desconocidas(datos, q)
    assert total == 0 or 2 * len(desconocidas) > total


@pytest.mark.parametrize("q", ["data mining", "sistema visual", "hidrología", "EEG", "procesamiento de imágenes",
                               "visualization of brain signals", "deep learnign", "IA en salud"])
def test_tema_real(datos, q):
    desconocidas, total = tema.palabras_desconocidas(datos, q)
    assert total and 2 * len(desconocidas) <= total


def test_alias_y_tildes():
    assert tema.habilidad_por_nombre("computacion grafica") == list(tema.HABILIDADES).index("Computación gráfica")
    assert tema.habilidad_por_nombre("IA") == list(tema.HABILIDADES).index("Machine learning")


def test_coincidencia_exige_todas_las_palabras():
    textos = [tema._tokens_texto("Collision Awareness System for the Mining Industry"),
              tema._tokens_texto("A systematic study of data mining"),
              tema._tokens_texto("Ingeniería de software")]
    c = tema._coincidencia(textos, "data mining")
    assert c[0] == 0 and c[1] == 1
    assert tema._coincidencia(textos, "ingeniería de software")[2] == 1


@pytest.mark.parametrize("q", ["cnn", "gnn", "vit", "BIM", "GAN", "LiDAR", "CRISPR", "PCR", "cnn for EEG"])
def test_siglas_no_son_basura(datos, q):
    desconocidas, total = tema.palabras_desconocidas(datos, q)
    assert total and not desconocidas


def test_sigla_exacta_y_expansion():
    textos = [tema._tokens_texto("Scaffold for in vitro culture"),
              tema._tokens_texto("Fuzzy Vision Transformer to decode sEMG"),
              tema._tokens_texto("A ViT model for skin lesions")]
    c = tema._coincidencia(textos, "vit")
    assert c[0] == 0 and c[1] == 1 and c[2] == 1      # «vit» no calza con «vitro»; sí con la sigla o su expansión
    assert tema.expandir_siglas("ViT para imágenes") == "vision transformer (ViT) para imágenes"
