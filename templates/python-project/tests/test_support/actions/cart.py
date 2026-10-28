"""Business vocabulary; no I/O and no hidden behavioral assertions."""

from test_support.contracts.observations import observed
from test_support.physical import cart as _driver


@observed
def quote_total(prices):
    return _driver.quote_total(prices)
