from hub.connectors.base import BaseConnector, FieldRegistry, FieldSpec


def test_registry_names_and_dict():
    reg = FieldRegistry([
        FieldSpec("date", "date", dimension=True),
        FieldSpec("clicks", "clicks"),
        FieldSpec("position", "position", description="avg SERP position"),
    ])
    assert reg.names() == ["date", "clicks", "position"]
    d = reg.to_dict()
    assert d[0] == {"name": "date", "native": "date", "dimension": True, "description": ""}
    assert d[2]["description"] == "avg SERP position"


def test_base_connector_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        BaseConnector(settings=None, secrets_dir=".")  # type: ignore[abstract]
