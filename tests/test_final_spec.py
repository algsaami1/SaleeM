from app.services.analyzer import load_final_spec


def test_final_spec_is_loaded():
    spec = load_final_spec()
    assert "تحليل SaleeM" in spec
    assert "عدد ثابت" in spec
    assert "TP1" in spec and "TP2" in spec and "TP3" in spec
