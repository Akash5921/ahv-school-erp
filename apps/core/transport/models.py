from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.academic_sessions.models import AcademicSession
from apps.core.schools.models import School
from apps.core.students.models import Student
from apps.core.utils.managers import SchoolManager


class Driver(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='transport_drivers',
    )
    objects = SchoolManager()

    name = models.CharField(max_length=120)
    license_number = models.CharField(max_length=80, unique=True)
    phone = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    joining_date = models.DateField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']
        indexes = [
            models.Index(fields=['school', 'is_active']),
        ]

    def clean(self):
        super().clean()
        self.name = (self.name or '').strip()
        self.license_number = (self.license_number or '').strip().upper()
        if not self.name:
            raise ValidationError({'name': 'Driver name is required.'})
        if not self.license_number:
            raise ValidationError({'license_number': 'License number is required.'})

    def delete(self, *args, **kwargs):
        if self.vehicles.filter(is_active=True).exists():
            raise ValidationError('Cannot delete driver while active vehicles are assigned.')
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active', 'updated_at'])

    def __str__(self):
        return f"{self.name} ({self.license_number})"


class Vehicle(models.Model):
    TYPE_BUS = 'bus'
    TYPE_VAN = 'van'
    TYPE_CHOICES = (
        (TYPE_BUS, 'Bus'),
        (TYPE_VAN, 'Van'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='transport_vehicles',
    )
    objects = SchoolManager()

    vehicle_number = models.CharField(max_length=50)
    vehicle_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_BUS)
    capacity = models.PositiveIntegerField()
    registration_number = models.CharField(max_length=120, blank=True)
    insurance_expiry = models.DateField(null=True, blank=True)
    fitness_expiry = models.DateField(null=True, blank=True)
    assigned_driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vehicles',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['vehicle_number', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'vehicle_number'],
                name='unique_vehicle_number_per_school',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'insurance_expiry']),
            models.Index(fields=['school', 'fitness_expiry']),
        ]

    def clean(self):
        super().clean()
        self.vehicle_number = (self.vehicle_number or '').strip().upper()
        self.registration_number = (self.registration_number or '').strip()

        if not self.vehicle_number:
            raise ValidationError({'vehicle_number': 'Vehicle number is required.'})
        if not self.capacity or self.capacity <= 0:
            raise ValidationError({'capacity': 'Capacity must be greater than zero.'})

        if self.assigned_driver_id:
            if self.assigned_driver.school_id != self.school_id:
                raise ValidationError({'assigned_driver': 'Assigned driver must belong to selected school.'})
            if not self.assigned_driver.is_active:
                raise ValidationError({'assigned_driver': 'Inactive driver cannot be assigned.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active', 'updated_at'])

    def __str__(self):
        return self.vehicle_number


class Route(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='transport_routes',
    )
    objects = SchoolManager()

    route_name = models.CharField(max_length=120)
    start_point = models.CharField(max_length=120)
    end_point = models.CharField(max_length=120)
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name='routes',
    )
    default_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['route_name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'route_name'],
                name='unique_route_name_per_school',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'vehicle']),
        ]

    def clean(self):
        super().clean()
        self.route_name = (self.route_name or '').strip()
        self.start_point = (self.start_point or '').strip()
        self.end_point = (self.end_point or '').strip()

        if not self.route_name:
            raise ValidationError({'route_name': 'Route name is required.'})
        if not self.start_point:
            raise ValidationError({'start_point': 'Start point is required.'})
        if not self.end_point:
            raise ValidationError({'end_point': 'End point is required.'})
        if self.default_fee is None or self.default_fee < 0:
            raise ValidationError({'default_fee': 'Default fee cannot be negative.'})

        if self.vehicle_id:
            if self.vehicle.school_id != self.school_id:
                raise ValidationError({'vehicle': 'Vehicle must belong to selected school.'})
            if not self.vehicle.is_active:
                raise ValidationError({'vehicle': 'Inactive vehicle cannot be assigned.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active', 'updated_at'])

    def __str__(self):
        return self.route_name


class RouteStop(models.Model):
    route = models.ForeignKey(
        Route,
        on_delete=models.CASCADE,
        related_name='stops',
    )
    stop_name = models.CharField(max_length=120)
    stop_order = models.PositiveIntegerField()

    class Meta:
        ordering = ['stop_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['route', 'stop_order'],
                name='unique_stop_order_per_route',
            ),
            models.UniqueConstraint(
                fields=['route', 'stop_name'],
                name='unique_stop_name_per_route',
            ),
        ]

    def clean(self):
        super().clean()
        self.stop_name = (self.stop_name or '').strip()
        if not self.stop_name:
            raise ValidationError({'stop_name': 'Stop name is required.'})
        if not self.stop_order or self.stop_order <= 0:
            raise ValidationError({'stop_order': 'Stop order must be greater than zero.'})

    def __str__(self):
        return f"{self.route.route_name} - {self.stop_name}"


class StudentTransport(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='student_transport_allocations',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='student_transport_allocations',
    )
    objects = SchoolManager()

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='transport_allocations',
    )
    route = models.ForeignKey(
        Route,
        on_delete=models.PROTECT,
        related_name='student_allocations',
    )
    stop_name = models.CharField(max_length=120)
    pickup_time = models.TimeField(null=True, blank=True)
    drop_time = models.TimeField(null=True, blank=True)
    transport_fee = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['student__admission_number', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'session'],
                condition=Q(is_active=True),
                name='unique_active_transport_per_student_session',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'is_active']),
            models.Index(fields=['school', 'route', 'is_active']),
        ]

    def clean(self):
        super().clean()
        self.stop_name = (self.stop_name or '').strip()

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})

        if self.student_id:
            if self.student.school_id != self.school_id:
                raise ValidationError({'student': 'Student must belong to selected school.'})
            if self.student.session_id != self.session_id:
                raise ValidationError({'student': 'Student must belong to selected session.'})
            if self.student.is_archived or not self.student.is_active or self.student.status != Student.STATUS_ACTIVE:
                raise ValidationError({'student': 'Only active students can be allocated to transport.'})

        if self.route_id:
            if self.route.school_id != self.school_id:
                raise ValidationError({'route': 'Route must belong to selected school.'})
            if not self.route.is_active:
                raise ValidationError({'route': 'Inactive route cannot be assigned.'})
            if not self.route.vehicle.is_active:
                raise ValidationError({'route': 'Route vehicle must be active.'})

        if not self.stop_name:
            raise ValidationError({'stop_name': 'Stop name is required.'})

        route_stops = self.route.stops.values_list('stop_name', flat=True) if self.route_id else []
        if route_stops and self.stop_name not in set(route_stops):
            raise ValidationError({'stop_name': 'Stop must be one of the configured route stops.'})

        if self.transport_fee is None or self.transport_fee < 0:
            raise ValidationError({'transport_fee': 'Transport fee cannot be negative.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active', 'updated_at'])

    def __str__(self):
        return f"{self.student.admission_number} - {self.route.route_name}"
