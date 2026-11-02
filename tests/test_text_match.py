from helpdesk.text_match import compile_terms, find_terms


def test_matches_whole_word_only():
    pattern = compile_terms(["agent"])
    assert find_terms(pattern, "Can I talk to an agent?") == ["agent"]
    assert find_terms(pattern, "I called the agency") == []
    assert find_terms(pattern, "your agents are slow") == []
    assert find_terms(pattern, "a chemical reagent") == []


def test_matches_multi_word_terms_and_ignores_case():
    pattern = compile_terms(["pessoa de verdade", "humano"])
    assert find_terms(pattern, "Quero uma PESSOA DE VERDADE") == ["pessoa de verdade"]


def test_handles_accented_words():
    pattern = compile_terms(["não liga"])
    assert find_terms(pattern, "Minha maquininha não liga") == ["não liga"]
    assert find_terms(pattern, "Minha maquininha não ligava") == []


def test_escapes_regex_characters():
    pattern = compile_terms(["2ª via"])
    assert find_terms(pattern, "Preciso da 2ª via do cartão") == ["2ª via"]
