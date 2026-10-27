import importlib

import pytest


@pytest.mark.parametrize("layer", ["domain", "application", "infrastructure", "interface"])
def test_layer_is_importable(layer: str) -> None:
    assert importlib.import_module(f"sobreplano.{layer}") is not None
