from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import logging
from typing import Iterable
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.dependencies.rate_limit import build_identity_key
from app.models.customer import Customer
from app.models.enums import (
    AppointmentStatus,
    BookingChannel,
    ChannelType,
    MessageDirection,
)
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.conversation_state_repository import ConversationStateRepository
from app.repositories.customer_identity_repository import CustomerIdentityRepository
from app.repositories.customer_repository import CustomerRepository
from app.repositories.message_log_repository import MessageLogRepository
from app.schemas.discovery import DiscoveryBookingCreate
from app.schemas.whatsapp import (
    WhatsAppButtonOption,
    WhatsAppInboundMessage,
    WhatsAppListRow,
    WhatsAppListSection,
    WhatsAppOutboundMessage,
)
from app.services.appointment_service import AppointmentService
from app.services.discovery_service import DiscoveryService
from app.services.observability.domain_events import record_domain_event
from app.services.observability.metrics import increment_counter
from app.services.rate_limiter import get_rate_limit_policy, rate_limiter
from app.services.whatsapp.gateway import WhatsAppGatewayError, WhatsAppCloudApiGateway
from app.utils.phone import normalize_phone_number

logger = logging.getLogger(__name__)

START_KEYWORDS = {"start", "restart", "hi", "hello"}
MENU_KEYWORDS = {"menu"}
BUTTON_TITLE_LIMIT = 20
LIST_TITLE_LIMIT = 24
LIST_DESC_LIMIT = 72


@dataclass
class WhatsAppProcessResult:
    processed_messages: int = 0
    duplicate_messages: int = 0
    outbound_sent: int = 0
    outbound_failed: int = 0


class WhatsAppService:
    def __init__(self, db: Session):
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.identity_repo = CustomerIdentityRepository(db)
        self.conversation_repo = ConversationStateRepository(db)
        self.message_log_repo = MessageLogRepository(db)
        self.appointment_repo = AppointmentRepository(db)
        self.discovery_service = DiscoveryService(db)
        self.appointment_service = AppointmentService(db)
        self.gateway = WhatsAppCloudApiGateway()

    def process_messages(self, messages: Iterable[WhatsAppInboundMessage]) -> WhatsAppProcessResult:
        summary = WhatsAppProcessResult()
        for message in messages:
            if not self._record_inbound_if_new(message):
                summary.duplicate_messages += 1
                continue
            summary.processed_messages += 1

            customer = self._resolve_customer(message.external_user_id)
            if customer is None:
                sent, failed = self._send_outbound_messages(
                    external_user_id=message.external_user_id,
                    customer_id=None,
                    organization_id=None,
                    provider_id=None,
                    responses=[
                        self._text_message(
                            "We could not verify your number for booking. Please contact support."
                        )
                    ],
                )
                summary.outbound_sent += sent
                summary.outbound_failed += failed
                continue

            self._ensure_identity(customer=customer, external_user_id=message.external_user_id)
            state = self._get_or_create_state(customer=customer, external_user_id=message.external_user_id)

            if not self._is_rate_limit_allowed(customer=customer, external_user_id=message.external_user_id):
                sent, failed = self._send_outbound_messages(
                    external_user_id=message.external_user_id,
                    customer_id=customer.id,
                    organization_id=state.selected_organization_id,
                    provider_id=state.selected_provider_id,
                    responses=[
                        self._text_message("Too many requests. Please wait a moment and try again.")
                    ],
                )
                summary.outbound_sent += sent
                summary.outbound_failed += failed
                continue

            responses = self._route_message(customer=customer, state=state, message=message)
            sent, failed = self._send_outbound_messages(
                external_user_id=message.external_user_id,
                customer_id=customer.id,
                organization_id=state.selected_organization_id,
                provider_id=state.selected_provider_id,
                responses=responses,
            )
            summary.outbound_sent += sent
            summary.outbound_failed += failed
        return summary

    def _record_inbound_if_new(self, message: WhatsAppInboundMessage) -> bool:
        try:
            self.message_log_repo.create(
                direction=MessageDirection.INBOUND,
                channel=ChannelType.WHATSAPP,
                external_message_id=message.external_message_id,
                payload_json=message.model_dump(mode="json"),
            )
            return True
        except IntegrityError:
            self.db.rollback()
            logger.info(
                "whatsapp_duplicate_inbound_ignored external_message_id=%s",
                message.external_message_id,
            )
            return False

    def _resolve_customer(self, external_user_id: str) -> Customer | None:
        identity = self.identity_repo.get_by_channel_external_user(ChannelType.WHATSAPP, external_user_id)
        if identity is not None:
            customer = self.customer_repo.get(identity.customer_id)
            if customer is not None:
                return customer

        try:
            normalized_phone = normalize_phone_number(external_user_id)
        except ValueError:
            return None

        customer = self.customer_repo.get_by_phone_normalized(normalized_phone)
        if customer is not None:
            return customer

        fallback_name = f"WhatsApp {normalized_phone[-4:]}"
        return self.customer_repo.create(
            full_name=fallback_name,
            phone_number=normalized_phone,
            email=None,
            preferred_language="en",
        )

    def _ensure_identity(self, *, customer: Customer, external_user_id: str) -> None:
        existing = self.identity_repo.get_by_channel_external_user(ChannelType.WHATSAPP, external_user_id)
        if existing is not None:
            return
        try:
            self.identity_repo.create(
                customer_id=customer.id,
                channel=ChannelType.WHATSAPP,
                external_user_id=external_user_id,
                external_chat_id=external_user_id,
            )
        except IntegrityError:
            self.db.rollback()

    def _get_or_create_state(self, *, customer: Customer, external_user_id: str):
        state = self.conversation_repo.get_by_customer_and_channel(
            customer_id=customer.id,
            channel=ChannelType.WHATSAPP,
        )
        if state is None:
            state = self.conversation_repo.create(
                customer_id=customer.id,
                channel=ChannelType.WHATSAPP,
                external_user_id=external_user_id,
                current_flow="menu",
                current_step="select_organization",
                context_json={},
            )
            return state
        self.conversation_repo.update(
            state,
            external_user_id=external_user_id,
        )
        return state

    def _is_rate_limit_allowed(self, *, customer: Customer, external_user_id: str) -> bool:
        policy = get_rate_limit_policy("whatsapp_inbound")
        decision = rate_limiter.check(
            policy=policy,
            key=build_identity_key([f"wa:{external_user_id}"]),
        )
        if decision.allowed:
            return True
        record_domain_event(
            self.db,
            event_type="rate_limit_exceeded",
            entity_type="customer",
            entity_id=customer.id,
            actor_type="customer",
            actor_id=customer.id,
            status="failure",
            payload={
                "policy": decision.policy_name,
                "retry_after_seconds": decision.retry_after_seconds,
                "backend": decision.backend,
                "key_fingerprint": decision.key_fingerprint,
                "channel": ChannelType.WHATSAPP.value,
            },
        )
        return False

    def _route_message(self, *, customer: Customer, state, message: WhatsAppInboundMessage) -> list[WhatsAppOutboundMessage]:
        text_value = (message.text_body or "").strip().lower()
        action_id = (message.action_id or "").strip()

        if text_value in START_KEYWORDS:
            return self._start_flow(customer=customer, state=state)
        if text_value in MENU_KEYWORDS:
            return self._show_menu_or_org_selection(state=state)

        if action_id:
            return self._handle_action_id(customer=customer, state=state, action_id=action_id)

        if message.message_type == "text":
            return self._show_menu_hint(state=state)

        return self._stale_action_response(state=state)

    def _start_flow(self, *, customer: Customer, state) -> list[WhatsAppOutboundMessage]:
        self.conversation_repo.update(
            state,
            current_flow="menu",
            current_step="select_organization",
            selected_organization_id=None,
            selected_provider_id=None,
            selected_service_id=None,
            selected_location_id=None,
            selected_slot_start=None,
            context_json={},
        )
        increment_counter("whatsapp_conversation_started_total")
        record_domain_event(
            self.db,
            event_type="whatsapp_conversation_started",
            entity_type="customer",
            entity_id=customer.id,
            actor_type="customer",
            actor_id=customer.id,
            status="success",
            payload={"channel": ChannelType.WHATSAPP.value},
        )
        org_messages = self._render_organization_selection(state=state)
        return [self._text_message("Welcome to BookPoint on WhatsApp."), *org_messages]

    def _show_menu_or_org_selection(self, *, state) -> list[WhatsAppOutboundMessage]:
        organization = self._get_selected_visible_organization(state)
        if organization is None:
            return self._render_organization_selection(state=state)
        return self._render_main_menu(state=state, organization_name=organization.name)

    def _show_menu_hint(self, *, state) -> list[WhatsAppOutboundMessage]:
        follow_up = self._show_menu_or_org_selection(state=state)
        return [self._text_message("Please use the menu buttons or list options."), *follow_up]

    def _stale_action_response(self, *, state) -> list[WhatsAppOutboundMessage]:
        follow_up = self._show_menu_or_org_selection(state=state)
        return [self._text_message("That option is no longer valid. Please choose again."), *follow_up]

    def _handle_action_id(self, *, customer: Customer, state, action_id: str) -> list[WhatsAppOutboundMessage]:
        try:
            if action_id.startswith("org:"):
                organization_id = int(action_id.split(":", 1)[1])
                return self._handle_organization_selection(state=state, organization_id=organization_id)
            if action_id == "menu:change_org":
                return self._render_organization_selection(state=state)
            if action_id == "menu:book":
                return self._begin_booking_flow(state=state)
            if action_id == "menu:upcoming":
                return self._show_upcoming_bookings(customer=customer, state=state)
            if action_id.startswith("loc:"):
                location_id = int(action_id.split(":", 1)[1])
                return self._handle_location_selection(state=state, location_id=location_id)
            if action_id.startswith("svc:"):
                service_id = int(action_id.split(":", 1)[1])
                return self._handle_service_selection(state=state, service_id=service_id)
            if action_id.startswith("prov:"):
                provider_id = int(action_id.split(":", 1)[1])
                return self._handle_provider_selection(state=state, provider_id=provider_id)
            if action_id.startswith("date:"):
                slot_date = date.fromisoformat(action_id.split(":", 1)[1])
                return self._handle_booking_date_selection(state=state, slot_date=slot_date)
            if action_id.startswith("slot:"):
                slot_timestamp = int(action_id.split(":", 1)[1])
                return self._handle_booking_slot_selection(state=state, slot_timestamp=slot_timestamp)
            if action_id.startswith("confirm_book:yes:"):
                slot_timestamp = int(action_id.split(":")[2])
                return self._confirm_booking(customer=customer, state=state, slot_timestamp=slot_timestamp)
            if action_id == "confirm_book:no":
                return self._render_booking_dates(state=state)
            if action_id.startswith("booking:"):
                appointment_id = int(action_id.split(":", 1)[1])
                return self._show_booking_actions(customer=customer, state=state, appointment_id=appointment_id)
            if action_id.startswith("booking_action:cancel:"):
                appointment_id = int(action_id.split(":")[2])
                return self._confirm_cancel_prompt(customer=customer, state=state, appointment_id=appointment_id)
            if action_id.startswith("confirm_cancel:yes:"):
                appointment_id = int(action_id.split(":")[2])
                return self._confirm_cancel(customer=customer, state=state, appointment_id=appointment_id)
            if action_id.startswith("confirm_cancel:no:"):
                appointment_id = int(action_id.split(":")[2])
                return self._show_booking_actions(customer=customer, state=state, appointment_id=appointment_id)
            if action_id.startswith("booking_action:reschedule:"):
                appointment_id = int(action_id.split(":")[2])
                return self._render_reschedule_dates(customer=customer, state=state, appointment_id=appointment_id)
            if action_id.startswith("resched_date:"):
                _, appointment_id_text, date_text = action_id.split(":", 2)
                return self._handle_reschedule_date_selection(
                    customer=customer,
                    state=state,
                    appointment_id=int(appointment_id_text),
                    slot_date=date.fromisoformat(date_text),
                )
            if action_id.startswith("resched_slot:"):
                _, appointment_id_text, slot_text = action_id.split(":", 2)
                return self._handle_reschedule_slot_selection(
                    customer=customer,
                    state=state,
                    appointment_id=int(appointment_id_text),
                    slot_timestamp=int(slot_text),
                )
            if action_id.startswith("confirm_reschedule:yes:"):
                _, _, appointment_id_text, slot_text = action_id.split(":", 3)
                return self._confirm_reschedule(
                    customer=customer,
                    state=state,
                    appointment_id=int(appointment_id_text),
                    slot_timestamp=int(slot_text),
                )
            if action_id.startswith("confirm_reschedule:no:"):
                _, _, appointment_id_text, _ = action_id.split(":", 3)
                return self._render_reschedule_dates(
                    customer=customer,
                    state=state,
                    appointment_id=int(appointment_id_text),
                )
        except (LookupError, ValueError):
            return self._stale_action_response(state=state)
        return self._stale_action_response(state=state)

    def _handle_organization_selection(self, *, state, organization_id: int) -> list[WhatsAppOutboundMessage]:
        organization = self.discovery_service.get_visible_organization(organization_id)
        if organization is None:
            return self._stale_action_response(state=state)
        self.conversation_repo.update(
            state,
            current_flow="menu",
            current_step="select_action",
            selected_organization_id=organization.id,
            selected_provider_id=None,
            selected_service_id=None,
            selected_location_id=None,
            selected_slot_start=None,
            context_json={},
        )
        return [
            self._text_message(f"Organization selected: {organization.name}."),
            *self._render_main_menu(state=state, organization_name=organization.name),
        ]

    def _render_organization_selection(self, *, state) -> list[WhatsAppOutboundMessage]:
        organizations = self.discovery_service.list_visible_organizations()
        if not organizations:
            return [self._text_message("No organizations are currently available.")]
        rows = [
            WhatsAppListRow(
                id=f"org:{org.id}",
                title=self._truncate(org.name, LIST_TITLE_LIMIT),
                description=self._truncate(org.city or org.business_type, LIST_DESC_LIMIT),
            )
            for org in organizations[:10]
        ]
        self.conversation_repo.update(
            state,
            current_flow="menu",
            current_step="select_organization",
            selected_organization_id=None,
            selected_provider_id=None,
            selected_service_id=None,
            selected_location_id=None,
            selected_slot_start=None,
            context_json={},
        )
        response = self._list_message(
            body="Choose an organization to continue.",
            list_button_text="Organizations",
            sections=[WhatsAppListSection(title="Organizations", rows=rows)],
        )
        if len(organizations) > 10:
            return [self._text_message("Showing first 10 organizations. Type menu to restart."), response]
        return [response]

    def _render_main_menu(self, *, state, organization_name: str) -> list[WhatsAppOutboundMessage]:
        self.conversation_repo.update(
            state,
            current_flow="menu",
            current_step="select_action",
            context_json={},
        )
        return [
            self._buttons_message(
                body=f"{organization_name}: choose an action.",
                buttons=[
                    WhatsAppButtonOption(id="menu:book", title="Book"),
                    WhatsAppButtonOption(id="menu:upcoming", title="My Bookings"),
                    WhatsAppButtonOption(id="menu:change_org", title="Change Org"),
                ],
            )
        ]

    def _begin_booking_flow(self, *, state) -> list[WhatsAppOutboundMessage]:
        organization = self._get_selected_visible_organization(state)
        if organization is None:
            return self._render_organization_selection(state=state)
        locations = self.discovery_service.list_visible_locations(organization.id)
        if not locations:
            return [
                self._text_message("No active locations are available for this organization."),
                *self._render_main_menu(state=state, organization_name=organization.name),
            ]
        if len(locations) == 1:
            location = locations[0]
            return self._render_service_selection(
                state=state,
                location_id=location.id,
                location_name=location.name,
            )
        rows = [
            WhatsAppListRow(
                id=f"loc:{location.id}",
                title=self._truncate(location.name, LIST_TITLE_LIMIT),
                description=self._truncate(location.city or location.address_line_1 or "Location", LIST_DESC_LIMIT),
            )
            for location in locations[:10]
        ]
        self.conversation_repo.update(
            state,
            current_flow="booking",
            current_step="select_location",
            selected_provider_id=None,
            selected_service_id=None,
            selected_location_id=None,
            selected_slot_start=None,
            context_json={},
        )
        return [
            self._list_message(
                body="Choose a location.",
                list_button_text="Locations",
                sections=[WhatsAppListSection(title="Locations", rows=rows)],
            )
        ]

    def _handle_location_selection(self, *, state, location_id: int) -> list[WhatsAppOutboundMessage]:
        organization = self._get_selected_visible_organization(state)
        if organization is None:
            return self._render_organization_selection(state=state)
        location = self.discovery_service.get_visible_location(location_id)
        if location.organization_id != organization.id:
            return self._stale_action_response(state=state)
        return self._render_service_selection(
            state=state,
            location_id=location.id,
            location_name=location.name,
        )

    def _render_service_selection(self, *, state, location_id: int, location_name: str) -> list[WhatsAppOutboundMessage]:
        services = [
            service
            for service in self.discovery_service.list_visible_services_for_location(location_id)
            if not service.requires_payment
        ]
        if not services:
            organization = self._get_selected_visible_organization(state)
            follow_up = (
                self._render_main_menu(state=state, organization_name=organization.name)
                if organization is not None
                else self._render_organization_selection(state=state)
            )
            return [self._text_message("No WhatsApp-eligible services found at this location."), *follow_up]
        rows = [
            WhatsAppListRow(
                id=f"svc:{service.id}",
                title=self._truncate(service.name, LIST_TITLE_LIMIT),
                description=self._truncate(f"{service.duration_minutes} min", LIST_DESC_LIMIT),
            )
            for service in services[:10]
        ]
        self.conversation_repo.update(
            state,
            current_flow="booking",
            current_step="select_service",
            selected_location_id=location_id,
            selected_service_id=None,
            selected_provider_id=None,
            selected_slot_start=None,
            context_json={},
        )
        return [
            self._text_message(f"Location selected: {location_name}."),
            self._list_message(
                body="Choose a service.",
                list_button_text="Services",
                sections=[WhatsAppListSection(title="Services", rows=rows)],
            ),
        ]

    def _handle_service_selection(self, *, state, service_id: int) -> list[WhatsAppOutboundMessage]:
        location_id = state.selected_location_id
        if location_id is None:
            return self._begin_booking_flow(state=state)
        services = [
            service
            for service in self.discovery_service.list_visible_services_for_location(location_id)
            if not service.requires_payment
        ]
        selected = next((service for service in services if service.id == service_id), None)
        if selected is None:
            return self._stale_action_response(state=state)
        providers = self.discovery_service.list_visible_providers_for_service_at_location(
            location_id=location_id,
            service_id=service_id,
        )
        if not providers:
            return [self._text_message("No providers are currently available for that service.")]
        rows = [
            WhatsAppListRow(
                id=f"prov:{provider.id}",
                title=self._truncate(provider.display_name, LIST_TITLE_LIMIT),
                description=self._truncate(provider.title or "Provider", LIST_DESC_LIMIT),
            )
            for provider in providers[:10]
        ]
        self.conversation_repo.update(
            state,
            current_flow="booking",
            current_step="select_provider",
            selected_service_id=service_id,
            selected_provider_id=None,
            selected_slot_start=None,
            context_json={},
        )
        return [
            self._list_message(
                body="Choose a provider.",
                list_button_text="Providers",
                sections=[WhatsAppListSection(title="Providers", rows=rows)],
            )
        ]

    def _handle_provider_selection(self, *, state, provider_id: int) -> list[WhatsAppOutboundMessage]:
        location_id = state.selected_location_id
        service_id = state.selected_service_id
        if location_id is None or service_id is None:
            return self._begin_booking_flow(state=state)
        providers = self.discovery_service.list_visible_providers_for_service_at_location(
            location_id=location_id,
            service_id=service_id,
        )
        selected = next((provider for provider in providers if provider.id == provider_id), None)
        if selected is None:
            return self._stale_action_response(state=state)
        self.conversation_repo.update(
            state,
            current_flow="booking",
            current_step="select_date",
            selected_provider_id=provider_id,
            selected_slot_start=None,
            context_json={},
        )
        return self._render_booking_dates(state=state)

    def _render_booking_dates(self, *, state) -> list[WhatsAppOutboundMessage]:
        organization = self._get_selected_visible_organization(state)
        if organization is None:
            return self._render_organization_selection(state=state)
        rows = [
            WhatsAppListRow(
                id=f"date:{slot_date.isoformat()}",
                title=slot_date.strftime("%a, %b %d"),
                description=slot_date.isoformat(),
            )
            for slot_date in self._build_next_dates(organization.timezone, days=7)
        ]
        self.conversation_repo.update(
            state,
            current_flow="booking",
            current_step="select_date",
            selected_slot_start=None,
            context_json={},
        )
        return [
            self._list_message(
                body="Choose a date.",
                list_button_text="Dates",
                sections=[WhatsAppListSection(title="Available dates", rows=rows)],
            )
        ]

    def _handle_booking_date_selection(self, *, state, slot_date: date) -> list[WhatsAppOutboundMessage]:
        provider_id = state.selected_provider_id
        service_id = state.selected_service_id
        location_id = state.selected_location_id
        if provider_id is None or service_id is None or location_id is None:
            return self._begin_booking_flow(state=state)
        slots = self.discovery_service.list_visible_slots(
            provider_id=provider_id,
            service_id=service_id,
            location_id=location_id,
            slot_date=slot_date,
        )
        if not slots:
            return [
                self._text_message("No slots available on that date. Please pick another date."),
                *self._render_booking_dates(state=state),
            ]
        rows = [
            WhatsAppListRow(
                id=f"slot:{int(self._as_utc(slot.start_datetime).timestamp())}",
                title=self._as_utc(slot.start_datetime).strftime("%H:%M UTC"),
                description=self._as_utc(slot.start_datetime).isoformat(),
            )
            for slot in slots[:10]
        ]
        self.conversation_repo.update(
            state,
            current_flow="booking",
            current_step="select_slot",
            selected_slot_start=None,
            context_json={"selected_date": slot_date.isoformat()},
        )
        return [
            self._list_message(
                body="Choose a time slot.",
                list_button_text="Slots",
                sections=[WhatsAppListSection(title=slot_date.isoformat(), rows=rows)],
            )
        ]

    def _handle_booking_slot_selection(self, *, state, slot_timestamp: int) -> list[WhatsAppOutboundMessage]:
        slot = self._resolve_slot_from_state(state=state, slot_timestamp=slot_timestamp)
        if slot is None:
            return self._stale_action_response(state=state)
        self.conversation_repo.update(
            state,
            current_flow="booking",
            current_step="confirm_booking",
            selected_slot_start=slot.start_datetime,
            context_json={"selected_date": slot.start_datetime.date().isoformat()},
        )
        return [
            self._buttons_message(
                body=(
                    "Confirm booking for "
                    f"{self._as_utc(slot.start_datetime).strftime('%Y-%m-%d %H:%M UTC')}?"
                ),
                buttons=[
                    WhatsAppButtonOption(id=f"confirm_book:yes:{slot_timestamp}", title="Confirm"),
                    WhatsAppButtonOption(id="confirm_book:no", title="Change Date"),
                ],
            )
        ]

    def _confirm_booking(self, *, customer: Customer, state, slot_timestamp: int) -> list[WhatsAppOutboundMessage]:
        slot = self._resolve_slot_from_state(state=state, slot_timestamp=slot_timestamp)
        if slot is None:
            return self._stale_action_response(state=state)
        provider_id = state.selected_provider_id
        service_id = state.selected_service_id
        location_id = state.selected_location_id
        organization_id = state.selected_organization_id
        if provider_id is None or service_id is None or location_id is None or organization_id is None:
            return self._begin_booking_flow(state=state)

        customer_name = customer.full_name.strip() if customer.full_name.strip() else f"WhatsApp {customer.id}"
        payload = DiscoveryBookingCreate(
            organization_id=organization_id,
            location_id=location_id,
            provider_id=provider_id,
            service_id=service_id,
            scheduled_start=slot.start_datetime,
            customer_name=customer_name,
            customer_phone=customer.phone_number,
            customer_email=customer.email,
            preferred_language=customer.preferred_language or "en",
        )
        try:
            appointment, _, _ = self.discovery_service.create_public_booking(
                payload,
                booking_channel=BookingChannel.WHATSAPP,
            )
        except (LookupError, ValueError):
            return self._stale_action_response(state=state)

        increment_counter("whatsapp_bookings_completed_total")
        record_domain_event(
            self.db,
            event_type="whatsapp_booking_completed",
            entity_type="appointment",
            entity_id=appointment.id,
            organization_id=appointment.organization_id,
            actor_type="customer",
            actor_id=customer.id,
            related_appointment_id=appointment.id,
            status="success",
            payload={"channel": ChannelType.WHATSAPP.value},
        )
        organization = self.discovery_service.get_visible_organization(organization_id)
        organization_name = organization.name if organization is not None else "Organization"
        self.conversation_repo.update(
            state,
            current_flow="menu",
            current_step="select_action",
            selected_provider_id=None,
            selected_service_id=None,
            selected_location_id=None,
            selected_slot_start=None,
            context_json={},
        )
        return [
            self._text_message(
                "Booking confirmed. "
                f"Reference: {appointment.booking_reference} at "
                f"{self._as_utc(appointment.start_datetime).strftime('%Y-%m-%d %H:%M UTC')}."
            ),
            *self._render_main_menu(state=state, organization_name=organization_name),
        ]

    def _show_upcoming_bookings(self, *, customer: Customer, state) -> list[WhatsAppOutboundMessage]:
        organization = self._get_selected_visible_organization(state)
        if organization is None:
            return self._render_organization_selection(state=state)

        appointments = self.appointment_repo.list_upcoming_for_customer(
            customer_id=customer.id,
            organization_id=organization.id,
            now_datetime=datetime.now(timezone.utc),
            limit=10,
        )
        if not appointments:
            return [
                self._text_message("You have no upcoming bookings in this organization."),
                *self._render_main_menu(state=state, organization_name=organization.name),
            ]

        rows = [
            WhatsAppListRow(
                id=f"booking:{appointment.id}",
                title=self._as_utc(appointment.start_datetime).strftime("%b %d %H:%M UTC"),
                description=self._truncate(
                    f"{appointment.provider.display_name} - {appointment.service.name if appointment.service else 'Service'}",
                    LIST_DESC_LIMIT,
                ),
            )
            for appointment in appointments
        ]
        self.conversation_repo.update(
            state,
            current_flow="upcoming",
            current_step="select_booking",
            context_json={},
        )
        return [
            self._list_message(
                body="Select a booking to manage.",
                list_button_text="Bookings",
                sections=[WhatsAppListSection(title="Upcoming bookings", rows=rows)],
            )
        ]

    def _show_booking_actions(self, *, customer: Customer, state, appointment_id: int) -> list[WhatsAppOutboundMessage]:
        appointment = self._get_manageable_appointment(customer=customer, appointment_id=appointment_id, state=state)
        if appointment is None:
            return self._stale_action_response(state=state)
        self.conversation_repo.update(
            state,
            current_flow="upcoming",
            current_step="select_booking_action",
            context_json={"appointment_id": appointment.id},
        )
        return [
            self._buttons_message(
                body=(
                    f"{self._as_utc(appointment.start_datetime).strftime('%Y-%m-%d %H:%M UTC')}. "
                    "Choose action."
                ),
                buttons=[
                    WhatsAppButtonOption(id=f"booking_action:cancel:{appointment.id}", title="Cancel"),
                    WhatsAppButtonOption(id=f"booking_action:reschedule:{appointment.id}", title="Reschedule"),
                    WhatsAppButtonOption(id="menu:upcoming", title="Back"),
                ],
            )
        ]

    def _confirm_cancel_prompt(self, *, customer: Customer, state, appointment_id: int) -> list[WhatsAppOutboundMessage]:
        appointment = self._get_manageable_appointment(customer=customer, appointment_id=appointment_id, state=state)
        if appointment is None:
            return self._stale_action_response(state=state)
        self.conversation_repo.update(
            state,
            current_flow="cancel",
            current_step="confirm_cancel",
            context_json={"appointment_id": appointment.id},
        )
        return [
            self._buttons_message(
                body="Are you sure you want to cancel this booking?",
                buttons=[
                    WhatsAppButtonOption(id=f"confirm_cancel:yes:{appointment.id}", title="Yes, Cancel"),
                    WhatsAppButtonOption(id=f"confirm_cancel:no:{appointment.id}", title="Keep"),
                ],
            )
        ]

    def _confirm_cancel(self, *, customer: Customer, state, appointment_id: int) -> list[WhatsAppOutboundMessage]:
        appointment = self._get_manageable_appointment(customer=customer, appointment_id=appointment_id, state=state)
        if appointment is None:
            return self._stale_action_response(state=state)
        if appointment.status == AppointmentStatus.CANCELLED:
            return [self._text_message("This booking is already cancelled.")]
        try:
            updated = self.appointment_service.cancel_appointment(
                appointment.id,
                actor_type="customer",
                actor_id=customer.id,
            )
        except ValueError:
            return [self._text_message("This booking can no longer be cancelled.")]

        increment_counter("whatsapp_cancellations_completed_total")
        record_domain_event(
            self.db,
            event_type="whatsapp_cancel_completed",
            entity_type="appointment",
            entity_id=updated.id,
            organization_id=updated.organization_id,
            actor_type="customer",
            actor_id=customer.id,
            related_appointment_id=updated.id,
            status="success",
            payload={"channel": ChannelType.WHATSAPP.value},
        )
        organization = self._get_selected_visible_organization(state)
        organization_name = organization.name if organization is not None else "Organization"
        self.conversation_repo.update(
            state,
            current_flow="menu",
            current_step="select_action",
            context_json={},
        )
        return [
            self._text_message("Booking cancelled successfully."),
            *self._render_main_menu(state=state, organization_name=organization_name),
        ]

    def _render_reschedule_dates(self, *, customer: Customer, state, appointment_id: int) -> list[WhatsAppOutboundMessage]:
        appointment = self._get_manageable_appointment(customer=customer, appointment_id=appointment_id, state=state)
        if appointment is None:
            return self._stale_action_response(state=state)
        if appointment.service_id is None:
            return [self._text_message("This booking cannot be rescheduled from WhatsApp.")]

        organization = self._get_selected_visible_organization(state)
        timezone_name = organization.timezone if organization is not None else "UTC"
        rows = [
            WhatsAppListRow(
                id=f"resched_date:{appointment.id}:{slot_date.isoformat()}",
                title=slot_date.strftime("%a, %b %d"),
                description=slot_date.isoformat(),
            )
            for slot_date in self._build_next_dates(timezone_name, days=7)
        ]
        self.conversation_repo.update(
            state,
            current_flow="reschedule",
            current_step="select_reschedule_date",
            context_json={"appointment_id": appointment.id},
        )
        return [
            self._list_message(
                body="Choose a new date.",
                list_button_text="Dates",
                sections=[WhatsAppListSection(title="Reschedule dates", rows=rows)],
            )
        ]

    def _handle_reschedule_date_selection(
        self,
        *,
        customer: Customer,
        state,
        appointment_id: int,
        slot_date: date,
    ) -> list[WhatsAppOutboundMessage]:
        appointment = self._get_manageable_appointment(customer=customer, appointment_id=appointment_id, state=state)
        if appointment is None or appointment.service_id is None:
            return self._stale_action_response(state=state)
        slots = self.discovery_service.list_visible_slots(
            provider_id=appointment.provider_id,
            service_id=appointment.service_id,
            location_id=appointment.location_id,
            slot_date=slot_date,
        )
        if not slots:
            return [
                self._text_message("No slots available on that date. Please choose another date."),
                *self._render_reschedule_dates(customer=customer, state=state, appointment_id=appointment_id),
            ]
        rows = [
            WhatsAppListRow(
                id=f"resched_slot:{appointment.id}:{int(self._as_utc(slot.start_datetime).timestamp())}",
                title=self._as_utc(slot.start_datetime).strftime("%H:%M UTC"),
                description=self._as_utc(slot.start_datetime).isoformat(),
            )
            for slot in slots[:10]
        ]
        self.conversation_repo.update(
            state,
            current_flow="reschedule",
            current_step="select_reschedule_slot",
            context_json={
                "appointment_id": appointment.id,
                "selected_date": slot_date.isoformat(),
            },
        )
        return [
            self._list_message(
                body="Choose a new slot.",
                list_button_text="Slots",
                sections=[WhatsAppListSection(title=slot_date.isoformat(), rows=rows)],
            )
        ]

    def _handle_reschedule_slot_selection(
        self,
        *,
        customer: Customer,
        state,
        appointment_id: int,
        slot_timestamp: int,
    ) -> list[WhatsAppOutboundMessage]:
        appointment = self._get_manageable_appointment(customer=customer, appointment_id=appointment_id, state=state)
        if appointment is None or appointment.service_id is None:
            return self._stale_action_response(state=state)
        slot = self._resolve_reschedule_slot(
            state=state,
            appointment=appointment,
            slot_timestamp=slot_timestamp,
        )
        if slot is None:
            return self._stale_action_response(state=state)
        self.conversation_repo.update(
            state,
            current_flow="reschedule",
            current_step="confirm_reschedule",
            selected_slot_start=slot.start_datetime,
            context_json={
                "appointment_id": appointment.id,
                "selected_date": slot.start_datetime.date().isoformat(),
            },
        )
        return [
            self._buttons_message(
                body=(
                    "Confirm new slot: "
                    f"{self._as_utc(slot.start_datetime).strftime('%Y-%m-%d %H:%M UTC')}?"
                ),
                buttons=[
                    WhatsAppButtonOption(
                        id=f"confirm_reschedule:yes:{appointment.id}:{slot_timestamp}",
                        title="Confirm",
                    ),
                    WhatsAppButtonOption(
                        id=f"confirm_reschedule:no:{appointment.id}:{slot_timestamp}",
                        title="Change Date",
                    ),
                ],
            )
        ]

    def _confirm_reschedule(
        self,
        *,
        customer: Customer,
        state,
        appointment_id: int,
        slot_timestamp: int,
    ) -> list[WhatsAppOutboundMessage]:
        appointment = self._get_manageable_appointment(customer=customer, appointment_id=appointment_id, state=state)
        if appointment is None or appointment.service_id is None:
            return self._stale_action_response(state=state)
        slot = self._resolve_reschedule_slot(
            state=state,
            appointment=appointment,
            slot_timestamp=slot_timestamp,
        )
        if slot is None:
            return self._stale_action_response(state=state)
        try:
            updated = self.appointment_service.reschedule_appointment(
                appointment.id,
                slot.start_datetime,
                actor_type="customer",
                actor_id=customer.id,
            )
        except ValueError:
            return [self._text_message("That slot is no longer available. Please choose again.")]

        increment_counter("whatsapp_reschedules_completed_total")
        record_domain_event(
            self.db,
            event_type="whatsapp_reschedule_completed",
            entity_type="appointment",
            entity_id=updated.id,
            organization_id=updated.organization_id,
            actor_type="customer",
            actor_id=customer.id,
            related_appointment_id=updated.id,
            status="success",
            payload={"channel": ChannelType.WHATSAPP.value},
        )
        organization = self._get_selected_visible_organization(state)
        organization_name = organization.name if organization is not None else "Organization"
        self.conversation_repo.update(
            state,
            current_flow="menu",
            current_step="select_action",
            selected_slot_start=None,
            context_json={},
        )
        return [
            self._text_message("Booking rescheduled successfully."),
            *self._render_main_menu(state=state, organization_name=organization_name),
        ]

    def _resolve_slot_from_state(self, *, state, slot_timestamp: int):
        provider_id = state.selected_provider_id
        service_id = state.selected_service_id
        location_id = state.selected_location_id
        context = state.context_json or {}
        selected_date_text = context.get("selected_date")
        if not isinstance(selected_date_text, str):
            return None
        try:
            slot_date = date.fromisoformat(selected_date_text)
        except ValueError:
            return None
        if provider_id is None or service_id is None or location_id is None:
            return None
        slots = self.discovery_service.list_visible_slots(
            provider_id=provider_id,
            service_id=service_id,
            location_id=location_id,
            slot_date=slot_date,
        )
        return next((slot for slot in slots if int(self._as_utc(slot.start_datetime).timestamp()) == slot_timestamp), None)

    def _resolve_reschedule_slot(self, *, state, appointment, slot_timestamp: int):
        context = state.context_json or {}
        selected_date_text = context.get("selected_date")
        if not isinstance(selected_date_text, str):
            return None
        try:
            slot_date = date.fromisoformat(selected_date_text)
        except ValueError:
            return None
        slots = self.discovery_service.list_visible_slots(
            provider_id=appointment.provider_id,
            service_id=appointment.service_id,
            location_id=appointment.location_id,
            slot_date=slot_date,
        )
        return next((slot for slot in slots if int(self._as_utc(slot.start_datetime).timestamp()) == slot_timestamp), None)

    def _get_manageable_appointment(self, *, customer: Customer, appointment_id: int, state):
        appointment = self.appointment_repo.get(appointment_id)
        if appointment is None:
            return None
        if appointment.customer_id != customer.id:
            return None
        if state.selected_organization_id is not None and appointment.organization_id != state.selected_organization_id:
            return None
        if appointment.status not in {
            AppointmentStatus.PENDING,
            AppointmentStatus.PENDING_PAYMENT,
            AppointmentStatus.CONFIRMED,
        }:
            return None
        if self._as_utc(appointment.start_datetime) < datetime.now(timezone.utc):
            return None
        return appointment

    def _get_selected_visible_organization(self, state):
        if state.selected_organization_id is None:
            return None
        return self.discovery_service.get_visible_organization(state.selected_organization_id)

    def _send_outbound_messages(
        self,
        *,
        external_user_id: str,
        customer_id: int | None,
        organization_id: int | None,
        provider_id: int | None,
        responses: list[WhatsAppOutboundMessage],
    ) -> tuple[int, int]:
        sent = 0
        failed = 0
        for response in responses:
            try:
                if response.message_type == "text":
                    gateway_response = self.gateway.send_text(to=external_user_id, body=response.body)
                elif response.message_type == "buttons":
                    gateway_response = self.gateway.send_buttons(
                        to=external_user_id,
                        body=response.body,
                        buttons=response.buttons,
                    )
                elif response.message_type == "list":
                    gateway_response = self.gateway.send_list(
                        to=external_user_id,
                        body=response.body,
                        list_button_text=response.list_button_text or "Options",
                        sections=response.list_sections,
                        header_text=response.header_text,
                        footer_text=response.footer_text,
                    )
                else:
                    raise WhatsAppGatewayError("Unsupported outbound message type.")

                self.message_log_repo.create(
                    customer_id=customer_id,
                    organization_id=organization_id,
                    provider_id=provider_id,
                    direction=MessageDirection.OUTBOUND,
                    channel=ChannelType.WHATSAPP,
                    external_message_id=gateway_response.external_message_id,
                    payload_json={
                        "request": response.model_dump(mode="json"),
                        "provider_response": gateway_response.provider_payload,
                    },
                )
                increment_counter("whatsapp_outbound_sent_total")
                sent += 1
            except Exception as exc:
                self.db.rollback()
                increment_counter("whatsapp_outbound_failed_total")
                record_domain_event(
                    self.db,
                    event_type="whatsapp_outbound_failed",
                    entity_type="customer" if customer_id is not None else None,
                    entity_id=customer_id,
                    organization_id=organization_id,
                    actor_type="system",
                    status="failure",
                    payload={
                        "error": str(exc),
                        "channel": ChannelType.WHATSAPP.value,
                        "message_type": response.message_type,
                    },
                )
                try:
                    self.message_log_repo.create(
                        customer_id=customer_id,
                        organization_id=organization_id,
                        provider_id=provider_id,
                        direction=MessageDirection.OUTBOUND,
                        channel=ChannelType.WHATSAPP,
                        external_message_id=None,
                        payload_json={
                            "request": response.model_dump(mode="json"),
                            "error": str(exc),
                        },
                    )
                except Exception:
                    self.db.rollback()
                failed += 1
        return sent, failed

    @staticmethod
    def _build_next_dates(timezone_name: str, *, days: int) -> list[date]:
        try:
            zone = ZoneInfo(timezone_name)
        except Exception:
            zone = timezone.utc
        start_date = datetime.now(timezone.utc).astimezone(zone).date()
        return [start_date + timedelta(days=offset) for offset in range(days)]

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _truncate(value: str | None, limit: int) -> str:
        source = (value or "").strip()
        if not source:
            return "-"
        return source[:limit]

    @staticmethod
    def _text_message(body: str) -> WhatsAppOutboundMessage:
        return WhatsAppOutboundMessage(message_type="text", body=body)

    @staticmethod
    def _buttons_message(body: str, buttons: list[WhatsAppButtonOption]) -> WhatsAppOutboundMessage:
        clamped = [WhatsAppButtonOption(id=button.id, title=button.title[:BUTTON_TITLE_LIMIT]) for button in buttons[:3]]
        return WhatsAppOutboundMessage(message_type="buttons", body=body, buttons=clamped)

    @staticmethod
    def _list_message(
        *,
        body: str,
        list_button_text: str,
        sections: list[WhatsAppListSection],
        header_text: str | None = None,
        footer_text: str | None = None,
    ) -> WhatsAppOutboundMessage:
        limited_sections: list[WhatsAppListSection] = []
        for section in sections[:10]:
            rows = [
                WhatsAppListRow(
                    id=row.id,
                    title=row.title[:LIST_TITLE_LIMIT],
                    description=(row.description or "")[:LIST_DESC_LIMIT] or None,
                )
                for row in section.rows[:10]
            ]
            limited_sections.append(WhatsAppListSection(title=section.title[:LIST_TITLE_LIMIT], rows=rows))
        return WhatsAppOutboundMessage(
            message_type="list",
            body=body,
            list_button_text=list_button_text[:BUTTON_TITLE_LIMIT] or "Options",
            list_sections=limited_sections,
            header_text=header_text,
            footer_text=footer_text,
        )
