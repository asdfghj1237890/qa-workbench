"""Only detached declared data crosses a public test action boundary."""

import pytest
from test_support.actions import testing


@pytest.mark.parametrize("kind", ["live", "callable", "foreign_dataclass", "dataclass_type"])
def test_live_and_undeclared_values_are_rejected(kind):
    with pytest.raises(TypeError, match="action returned a live/unsupported object"):
        testing.observation(kind)


def test_mutating_detached_contract_data_cannot_change_the_original():
    result = testing.observation("detached")
    assert result["original"] == [{"value": "original"}]
    assert result["detached"] == [{"value": "changed"}]
    assert result["same"] is False
