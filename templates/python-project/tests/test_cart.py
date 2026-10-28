"""A scenario states expected behavior through public business actions."""

import pytest
from test_support.actions import cart


def test_cart_total_includes_every_item():
    assert cart.quote_total([10, 20]) == 30


def test_cart_rejects_a_negative_price():
    with pytest.raises(ValueError, match="negative_price"):
        cart.quote_total([10, -1])
