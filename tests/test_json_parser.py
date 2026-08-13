from services.json_parser import parse_model_json


def test_parse_plain_json():
    result = parse_model_json('{"a": 1}')
    assert result.success
    assert result.data == {"a": 1}
    assert result.method == "json.loads"


def test_parse_markdown_fenced_json():
    raw = '```json\n{"a": 1, "b": 2}\n```'
    result = parse_model_json(raw)
    assert result.success
    assert result.data == {"a": 1, "b": 2}
    assert result.method == "markdown_strip"


def test_parse_with_surrounding_text():
    raw = 'İşte sonuç:\n{"a": 1}\nUmarım yardımcı olur.'
    result = parse_model_json(raw)
    assert result.success
    assert result.data == {"a": 1}


def test_parse_repairs_broken_json():
    raw = "{'a': 1, 'b': 2,}"
    result = parse_model_json(raw)
    assert result.success
    assert result.data == {"a": 1, "b": 2}


def test_parse_empty_input_fails():
    result = parse_model_json("")
    assert not result.success
    assert result.error is not None


def test_parse_unrecoverable_fails():
    result = parse_model_json("bu hiç json değil ve düzeltilemez ][")
    assert not result.success
