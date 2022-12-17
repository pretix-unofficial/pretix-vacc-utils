import logging
from datetime import datetime, timedelta
from decimal import Decimal
from django.db import transaction
from django.db.models import Q
from django.utils.formats import date_format
from django.utils.timezone import make_aware, now
from django.utils.translation import gettext_lazy as _
from pretix.base.email import get_email_context
from pretix.base.i18n import language
from pretix.base.models import Order, OrderPosition, Quota
from pretix.base.services.locking import LockTimeoutException
from pretix.base.services.mail import SendMailException, TolerantDict
from pretix.base.services.tasks import EventTask
from pretix.base.signals import order_paid, order_placed
from pretix.celery_app import app

from pretix_vacc_autosched.forms import can_use_juvare_api
from pretix_vacc_autosched.models import LinkedOrderPosition

logger = logging.getLogger(__name__)


def get_for_other_event(op, event, prefer_second_item):
    logger.info(f"SECOND DOSE: Looking up item for event {event.slug}, prefer item {prefer_second_item}")
    if prefer_second_item:
        target_item = prefer_second_item
        if event != target_item.event:
            logger.info(f"SECOND DOSE: Abort because preferred item is for event {target_item.event.slug}")
            return None, None
    elif op.order.event == event:
        logger.info(f"SECOND DOSE: Choose same item because of same event")
        return op.item, op.variation
    else:
        possible_items = [
            n
            for n in event.items.all()
            if (n.internal_name or str(n.name))
            == (op.item.internal_name or str(op.item.name))
        ]
        if len(possible_items) != 1:
            op.order.log_action(
                "pretix_vacc_autosched.failed",
                data={
                    "reason": _("No product found"),
                    "position": op.pk,
                },
            )
            logger.info(f"SECOND DOSE: Possible items by name: {repr([n.pk for n in possible_items])}")
            return None, None

        target_item = possible_items[0]

    if op.variation or target_item.variations.exists():
        possible_variations = [
            n
            for n in target_item.variations.all()
            if str(n.value) == (str(op.variation.value) if op.variation else None)
        ]
        if len(possible_variations) != 1:
            logger.info(f"SECOND DOSE: Possible variations by name: {repr([n.pk for n in possible_variations])}")
            op.order.log_action(
                "pretix_vacc_autosched.failed",
                data={
                    "reason": _("No product variation found"),
                    "position": op.pk,
                },
            )
            return None, None
        target_var = possible_variations[0]
    else:
        target_var = None
    return target_item, target_var


@app.task(base=EventTask, bind=True, max_retries=5, default_retry_delay=60)
def schedule_second_dose(self, event, op):
    op = OrderPosition.objects.select_related(
        "item", "variation", "subevent", "order"
    ).get(pk=op)

    logger.info(f"SECOND DOSE: Scheduling started for {op.order.code}")

    if LinkedOrderPosition.objects.filter(
        Q(base_position=op) | Q(child_position=op)
    ).exists():
        logger.info("SECOND DOSE: Scheduling aborted, seond dose already booked")
        return

    itemconf = op.item.vacc_autosched_config
    earliest_date = make_aware(
        datetime.combine(
            op.subevent.date_from.astimezone(event.timezone).date()
            + timedelta(days=itemconf.days),
            op.subevent.date_from.astimezone(event.timezone).time(),
        ),
        event.timezone,
    )

    target_event = itemconf.event or event
    target_item, target_var = get_for_other_event(
        op, target_event, itemconf.second_item
    )

    logger.info(f"SECOND DOSE: date after {earliest_date}, target_event {target_event.slug}, target_item {target_item.pk if target_item else None}, target_variation {target_var.pk if target_var else None}")

    if target_item is None:
        return

    for i in range(250):  # max number of subevents to check
        subevent = (
            target_event.subevents.filter(
                date_from__gte=earliest_date,
            )
            .order_by("date_from")
            .first()
        )
        if not subevent:
            logger.info(f"SECOND DOSE: no time slot found after {earliest_date}")
            op.order.log_action(
                "pretix_vacc_autosched.failed",
                data={
                    "reason": _("No available time slot found"),
                    "position": op.pk,
                },
            )
            return

        try:
            order = book_second_dose(
                op=op,
                item=target_item,
                variation=target_var,
                subevent=subevent,
                original_event=event,
            )
            if not order:
                earliest_date = subevent.date_from + timedelta(minutes=1)
                continue
            else:
                return
        except LockTimeoutException:
            self.retry()

    logger.info(f"SECOND DOSE: no available time slot found after 250 tries")
    op.order.log_action(
        "pretix_vacc_autosched.failed",
        data={
            "reason": _("No available time slot found"),
            "position": op.pk,
            "last_looked_at": subevent.pk,
        },
    )
    return


def book_second_dose(*, op, item, variation, subevent, original_event):
    event = item.event
    with event.lock(), transaction.atomic():
        avcode, avnr = item.check_quotas(subevent=subevent, fail_on_no_quotas=True)
        if avcode != Quota.AVAILABILITY_OK:
            logger.info(f"SECOND DOSE: cannot use slot {subevent.pk}, sold out")
            # sold out, look for next one
            return

        childorder = Order.objects.create(
            event=event,
            status=Order.STATUS_PAID,
            require_approval=False,
            testmode=op.order.testmode,
            email=op.order.email,
            phone=op.order.phone,
            locale=op.order.locale,
            expires=now() + timedelta(days=30),
            total=Decimal("0.00"),
            expiry_reminder_sent=True,
            sales_channel=op.order.sales_channel,
            comment="Auto-generated through scheduling from order {}".format(
                op.order.code
            ),
            meta_info=op.order.meta_info,
        )
        op.order.log_action(
            "pretix_vacc_autosched.scheduled",
            data={
                "position": op.pk,
                "event": event.pk,
                "event_slug": event.slug,
                "order": childorder.code,
            },
        )
        childorder.log_action(
            "pretix_vacc_autosched.created",
            data={
                "event": original_event.pk,
                "event_slug": original_event.slug,
                "order": op.order.code,
            },
        )
        childorder.log_action(
            "pretix.event.order.placed", data={"source": "vacc_autosched"}
        )
        childpos = childorder.positions.create(
            positionid=1,
            tax_rate=Decimal("0.00"),
            tax_rule=None,
            tax_value=Decimal("0.00"),
            subevent=subevent,
            item=item,
            variation=variation,
            price=Decimal("0.00"),
            attendee_name_cached=op.attendee_name_cached,
            attendee_name_parts=op.attendee_name_parts,
            attendee_email=op.attendee_email,
            company=op.company,
            street=op.street,
            zipcode=op.zipcode,
            city=op.city,
            country=op.country,
            state=op.state,
            addon_to=None,
            voucher=None,
            meta_info=op.meta_info,
        )
        for answ in op.answers.all():
            q = childorder.event.questions.filter(
                identifier=answ.question.identifier
            ).first()
            if not q:
                continue
            childansw = childpos.answers.create(
                question=q, answer=answ.answer, file=answ.file
            )
            if answ.options.all():
                childopts = list(
                    q.options.filter(
                        identifier__in=[o.identifier for o in answ.options.all()]
                    )
                )
                if childopts:
                    childansw.options.add(*childopts)

        LinkedOrderPosition.objects.create(base_position=op, child_position=childpos)
        childorder.create_transactions(is_new=True)
    order_placed.send(event, order=childorder)
    order_paid.send(event, order=childorder)

    if original_event.settings.vacc_autosched_mail:
        with language(childorder.locale, original_event.settings.region):
            email_template = original_event.settings.vacc_autosched_body
            email_subject = str(original_event.settings.vacc_autosched_subject)

            email_context = get_email_context(event=childorder.event, order=childorder)
            email_context["scheduled_datetime"] = date_format(
                subevent.date_from.astimezone(original_event.timezone),
                "SHORT_DATETIME_FORMAT",
            )
            try:
                childorder.send_mail(
                    email_subject,
                    email_template,
                    email_context,
                    "pretix.event.order.email.order_placed",
                    attach_tickets=True,
                    attach_ical=event.settings.mail_attach_ical,
                )
            except SendMailException:
                logger.exception("Order approved email could not be sent")
    if (
        original_event.settings.vacc_autosched_sms
        and can_use_juvare_api(original_event)
        and childorder.phone
    ):
        with language(childorder.locale, original_event.settings.region):
            from pretix_juvare_notify.tasks import juvare_send_text

            template = original_event.settings.vacc_autosched_sms_text
            context = get_email_context(event=childorder.event, order=childorder)
            context["scheduled_datetime"] = date_format(
                subevent.date_from.astimezone(original_event.timezone),
                "SHORT_DATETIME_FORMAT",
            )
            message = str(template).format_map(TolerantDict(context))
            juvare_send_text.apply_async(
                kwargs={
                    "text": message,
                    "to": childorder.phone,
                    "event": original_event.pk,
                }
            )
    logger.info(f"SECOND DOSE: done, created order {childorder.code}")
    return childorder
