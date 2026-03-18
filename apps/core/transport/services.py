from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.core.fees.models import FeePaymentAllocation, FeeType, StudentFee

from .models import Driver, StudentTransport, Vehicle


def _to_decimal(value) -> Decimal:
    return Decimal(str(value or '0'))


def _quantize(value) -> Decimal:
    return _to_decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _transport_fee_type(school):
    fee_type, _ = FeeType.objects.get_or_create(
        school=school,
        name='Transport Fee',
        defaults={
            'category': FeeType.CATEGORY_TRANSPORT,
            'is_active': True,
        },
    )
    updates = []
    if fee_type.category != FeeType.CATEGORY_TRANSPORT:
        fee_type.category = FeeType.CATEGORY_TRANSPORT
        updates.append('category')
    if not fee_type.is_active:
        fee_type.is_active = True
        updates.append('is_active')
    if updates:
        fee_type.save(update_fields=updates)
    return fee_type


@transaction.atomic
def sync_student_transport_fee(*, allocation: StudentTransport):
    fee_type = _transport_fee_type(allocation.school)
    student = allocation.student

    if allocation.is_active:
        amount = _quantize(allocation.transport_fee)
        student_fee, _ = StudentFee.objects.update_or_create(
            school=allocation.school,
            session=allocation.session,
            student=student,
            fee_type=fee_type,
            is_carry_forward=False,
            defaults={
                'assigned_class': student.current_class,
                'total_amount': amount,
                'concession_amount': Decimal('0.00'),
                'final_amount': amount,
                'is_active': True,
            },
        )
        return student_fee

    StudentFee.objects.filter(
        school=allocation.school,
        session=allocation.session,
        student=student,
        fee_type=fee_type,
        is_carry_forward=False,
        is_active=True,
    ).update(is_active=False)
    return None


@transaction.atomic
def assign_student_transport(
    *,
    school,
    session,
    student,
    route,
    stop_name,
    pickup_time=None,
    drop_time=None,
    transport_fee=None,
):
    if student.school_id != school.id or session.school_id != school.id or route.school_id != school.id:
        raise ValidationError('School mismatch in transport allocation.')
    if student.session_id != session.id:
        raise ValidationError('Student must belong to selected session.')

    fee_value = _quantize(transport_fee if transport_fee is not None else route.default_fee)

    allocation = StudentTransport.objects.filter(
        school=school,
        session=session,
        student=student,
    ).order_by('-is_active', '-id').first()

    if allocation:
        allocation.route = route
        allocation.stop_name = stop_name
        allocation.pickup_time = pickup_time
        allocation.drop_time = drop_time
        allocation.transport_fee = fee_value
        allocation.is_active = True
        allocation.full_clean()
        allocation.save()
    else:
        allocation = StudentTransport.objects.create(
            school=school,
            session=session,
            student=student,
            route=route,
            stop_name=stop_name,
            pickup_time=pickup_time,
            drop_time=drop_time,
            transport_fee=fee_value,
            is_active=True,
        )

    StudentTransport.objects.filter(
        school=school,
        session=session,
        student=student,
        is_active=True,
    ).exclude(pk=allocation.pk).update(is_active=False)

    if not student.transport_assigned:
        student.transport_assigned = True
        student.save(update_fields=['transport_assigned', 'updated_at'])

    sync_student_transport_fee(allocation=allocation)
    return allocation


@transaction.atomic
def deactivate_student_transport(*, allocation: StudentTransport):
    if not allocation.is_active:
        return allocation

    allocation.is_active = False
    allocation.full_clean()
    allocation.save(update_fields=['is_active', 'updated_at'])

    active_exists = StudentTransport.objects.filter(
        school=allocation.school,
        session=allocation.session,
        student=allocation.student,
        is_active=True,
    ).exists()

    if active_exists:
        active_allocation = StudentTransport.objects.filter(
            school=allocation.school,
            session=allocation.session,
            student=allocation.student,
            is_active=True,
        ).order_by('-id').first()
        sync_student_transport_fee(allocation=active_allocation)
    else:
        allocation.student.transport_assigned = False
        allocation.student.save(update_fields=['transport_assigned', 'updated_at'])
        sync_student_transport_fee(allocation=allocation)

    return allocation


def route_wise_students(*, school, session):
    rows = StudentTransport.objects.filter(
        school=school,
        session=session,
        is_active=True,
    ).select_related(
        'student',
        'route',
        'route__vehicle',
        'route__vehicle__assigned_driver',
    ).order_by('route__route_name', 'student__admission_number')
    return list(rows)


def vehicle_occupancy_report(*, school, session):
    rows = []
    vehicles = Vehicle.objects.filter(school=school).select_related('assigned_driver').order_by('vehicle_number')
    for vehicle in vehicles:
        occupied = StudentTransport.objects.filter(
            school=school,
            session=session,
            is_active=True,
            route__vehicle=vehicle,
        ).count()
        rows.append({
            'vehicle': vehicle,
            'capacity': vehicle.capacity,
            'occupied': occupied,
            'available': max(vehicle.capacity - occupied, 0),
            'occupancy_percent': 0 if vehicle.capacity <= 0 else round((occupied / vehicle.capacity) * 100, 2),
        })
    return rows


def driver_allocation_report(*, school):
    rows = []
    drivers = Driver.objects.filter(school=school).order_by('name')
    for driver in drivers:
        vehicles = list(driver.vehicles.filter(school=school).order_by('vehicle_number'))
        route_count = sum(vehicle.routes.filter(is_active=True).count() for vehicle in vehicles)
        rows.append({
            'driver': driver,
            'vehicle_count': len(vehicles),
            'route_count': route_count,
            'vehicles': vehicles,
        })
    return rows


def insurance_expiry_report(*, school, days=30):
    today = timezone.localdate()
    horizon = today + timedelta(days=days)
    rows = Vehicle.objects.filter(
        school=school,
        insurance_expiry__isnull=False,
        insurance_expiry__lte=horizon,
    ).select_related('assigned_driver').order_by('insurance_expiry', 'vehicle_number')
    return list(rows)


def transport_fee_pending_report(*, school, session):
    rows = []
    transport_fee_rows = StudentFee.objects.filter(
        school=school,
        session=session,
        is_active=True,
        is_carry_forward=False,
        fee_type__category=FeeType.CATEGORY_TRANSPORT,
    ).select_related('student', 'fee_type').order_by('student__admission_number')

    for row in transport_fee_rows:
        paid = FeePaymentAllocation.objects.filter(
            student_fee=row,
            payment__is_reversed=False,
        ).aggregate(total=Sum('amount')).get('total') or Decimal('0.00')
        paid = _quantize(paid)
        final_amount = _quantize(row.final_amount)
        pending = _quantize(final_amount - paid)
        if pending <= 0:
            continue
        rows.append({
            'student_fee': row,
            'student': row.student,
            'total': final_amount,
            'paid': paid,
            'pending': pending,
        })
    return rows
