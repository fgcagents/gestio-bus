from ui_operativa import (
    netejar_i_filtrar_matricula,
    seleccionar_candidat_ocr,
)


def test_ocr_extreu_una_matricula_valida():
    assert netejar_i_filtrar_matricula("Bus 1234 BCD") == "1234BCD"


def test_ocr_corregeix_confusions_visuals_per_posicio():
    assert netejar_i_filtrar_matricula("I234 BC8") == "1234BCB"


def test_ocr_no_converteix_text_arbitrari_en_matricula():
    assert netejar_i_filtrar_matricula("AUTOBUS BARCELONA") == ""


def test_ocr_prioritza_confianca_i_no_concatena_fragments():
    resultats = [
        ([[0, 0], [20, 0], [20, 10], [0, 10]], "1234", 0.99),
        ([[40, 0], [60, 0], [60, 10], [40, 10]], "BCD", 0.99),
        ([[30, 20], [90, 20], [90, 40], [30, 40]], "5678FGH", 0.90),
    ]
    candidat, confianca = seleccionar_candidat_ocr(resultats, (120, 60))
    assert candidat == "5678FGH"
    assert confianca == 0.90
