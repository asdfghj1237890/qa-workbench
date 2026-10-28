"""Replace this sample with your system's public application boundary."""


def cart_total(prices):
    if any(price < 0 for price in prices):
        raise ValueError("negative_price")
    return sum(prices)
