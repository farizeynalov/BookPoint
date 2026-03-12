from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.models.enums import CommissionType


def validate_organization_commission_config(
    *,
    commission_type: CommissionType,
    commission_percentage: Decimal | float | int | None,
    commission_fixed_minor: int | None,
) -> None:
    if commission_fixed_minor is None:
        raise ValueError("commission_fixed_minor is required.")
    if commission_fixed_minor < 0:
        raise ValueError("commission_fixed_minor must be non-negative.")

    if commission_percentage is None:
        raise ValueError("commission_percentage is required.")
    percentage_decimal = Decimal(str(commission_percentage))
    if percentage_decimal < Decimal("0") or percentage_decimal > Decimal("1"):
        raise ValueError("commission_percentage must be between 0 and 1.")

    if commission_type == CommissionType.FIXED:
        return
    if commission_type == CommissionType.PERCENTAGE:
        return
    raise ValueError("Unsupported commission_type.")


def calculate_platform_fee_minor(
    *,
    amount_minor: int,
    commission_type: CommissionType,
    commission_percentage: Decimal | float | int | None,
    commission_fixed_minor: int | None,
) -> int:
    if amount_minor <= 0:
        return 0

    validate_organization_commission_config(
        commission_type=commission_type,
        commission_percentage=commission_percentage,
        commission_fixed_minor=commission_fixed_minor,
    )

    if commission_type == CommissionType.FIXED:
        return min(max(int(commission_fixed_minor or 0), 0), amount_minor)

    percentage_decimal = Decimal(str(commission_percentage))
    fee = (Decimal(amount_minor) * percentage_decimal).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return min(max(int(fee), 0), amount_minor)
