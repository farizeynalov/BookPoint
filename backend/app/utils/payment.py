from decimal import Decimal, ROUND_HALF_UP

from app.models.enums import PaymentType

ZERO_DECIMAL_CURRENCIES = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}


def currency_minor_exponent(currency: str) -> int:
    return 0 if currency.upper() in ZERO_DECIMAL_CURRENCIES else 2


def decimal_to_minor(amount: Decimal, currency: str) -> int:
    multiplier = Decimal(10) ** currency_minor_exponent(currency)
    normalized = (amount * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(normalized)


def validate_service_payment_policy(
    *,
    requires_payment: bool,
    payment_type: PaymentType,
    price: Decimal | None,
    currency: str | None,
    deposit_amount_minor: int | None,
) -> None:
    if not requires_payment:
        if deposit_amount_minor is not None:
            raise ValueError("deposit_amount_minor must be null when requires_payment is false.")
        return

    if price is None:
        raise ValueError("price is required when requires_payment is true.")
    if currency is None or not currency.strip():
        raise ValueError("currency is required when requires_payment is true.")

    price_minor = decimal_to_minor(price, currency)
    if payment_type == PaymentType.DEPOSIT:
        if deposit_amount_minor is None:
            raise ValueError("deposit_amount_minor is required when payment_type is deposit.")
        if deposit_amount_minor <= 0:
            raise ValueError("deposit_amount_minor must be greater than zero.")
        if deposit_amount_minor > price_minor:
            raise ValueError("deposit_amount_minor must be less than or equal to service price.")
        return

    if deposit_amount_minor is not None:
        raise ValueError("deposit_amount_minor must be null when payment_type is full.")
