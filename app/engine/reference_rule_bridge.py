from app.engine.reference_rule_catalog import load_reference_rules

def _text(v):
    return str(v or "").lower().replace("_", " ").replace("-", " ")

def match_reference(name, bias=""):
    name = _text(name)
    bias = _text(bias)
    best = None
    best_score = 0

    for r in load_reference_rules():
        text = " ".join([
            _text(r.get("id")),
            _text(r.get("name_ar")),
            _text(r.get("family")),
            " ".join(_text(x) for x in r.get("aliases", [])),
        ])

        score = 0

        if name and name in text:
            score += 70

        rbias = _text(r.get("bias"))
        if bias and bias in rbias:
            score += 20

        if score > best_score:
            best_score = score
            best = r

    if not best or best_score < 50:
        return None

    return {
        "id": best.get("id", ""),
        "name": best.get("name_ar", ""),
        "family": best.get("family", ""),
        "score": min(100, best_score),
    }
