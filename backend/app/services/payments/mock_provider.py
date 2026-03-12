from __future__ import annotations

import secrets

from app.models.enums import PaymentStatus, RefundStatus


class MockCheckoutProvider:
    name = "mock"

    def create_checkout_session(
        self,
        *,
        payment_id: int,
        amount_minor: int,
        currency: str,
        appointment_id: int,
    ) -> dict[str, str]:
        session_id = f"mock_cs_{secrets.token_hex(12)}"
        payment_intent_id = f"mock_pi_{secrets.token_hex(12)}"
        checkout_url = f"https://mock-pay.bookpoint.local/checkout/{session_id}"
        return {
            "provider_name": self.name,
            "checkout_session_id": session_id,
            "payment_intent_id": payment_intent_id,
            "checkout_url": checkout_url,
            "status": PaymentStatus.REQUIRES_ACTION.value,
            "appointment_id": str(appointment_id),
            "amount_minor": str(amount_minor),
            "currency": currency.upper(),
            "payment_id": str(payment_id),
        }


class MockRefundProvider:
    name = "mock"

    def create_refund(
        self,
        *,
        payment_id: int,
        amount_minor: int,
        currency: str,
    ) -> dict[str, str]:
        refund_id = f"mock_rf_{secrets.token_hex(12)}"
        return {
            "provider_name": self.name,
            "provider_refund_id": refund_id,
            "status": RefundStatus.SUCCEEDED.value,
            "payment_id": str(payment_id),
            "amount_minor": str(amount_minor),
            "currency": currency.upper(),
        }
