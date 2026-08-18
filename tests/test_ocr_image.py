from ui_operativa import netejar_i_filtrar_matricula


def test_ocr_extreu_una_matricula_valida():
    assert netejar_i_filtrar_matricula("Bus 1234 BCD") == "1234BCD"


def test_ocr_corregeix_confusions_visuals_per_posicio():
    assert netejar_i_filtrar_matricula("I234 BC8") == "1234BCB"


def test_ocr_no_converteix_text_arbitrari_en_matricula():
    assert netejar_i_filtrar_matricula("AUTOBUS BARCELONA") == ""
