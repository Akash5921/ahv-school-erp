from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.hr.models import Staff
from apps.core.schools.models import School
from apps.core.students.models import Student
from apps.core.utils.managers import SchoolManager


class Asset(models.Model):
    CONDITION_GOOD = 'good'
    CONDITION_DAMAGED = 'damaged'
    CONDITION_REPAIR = 'repair'
    CONDITION_CHOICES = (
        (CONDITION_GOOD, 'Good'),
        (CONDITION_DAMAGED, 'Damaged'),
        (CONDITION_REPAIR, 'Repair'),
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='assets_core',
    )
    objects = SchoolManager()

    asset_name = models.CharField(max_length=150)
    asset_code = models.CharField(max_length=60)
    category = models.CharField(max_length=120)
    purchase_date = models.DateField(null=True, blank=True)
    purchase_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    location = models.CharField(max_length=120, blank=True)
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default=CONDITION_GOOD)
    assigned_to = models.ForeignKey(
        Staff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_assets',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['asset_name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'asset_code'],
                name='unique_asset_code_per_school',
            ),
            models.CheckConstraint(
                condition=Q(purchase_cost__gte=0),
                name='asset_purchase_cost_non_negative',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'category']),
        ]

    def clean(self):
        super().clean()
        self.asset_name = (self.asset_name or '').strip()
        self.asset_code = (self.asset_code or '').strip().upper()
        self.category = (self.category or '').strip()
        self.location = (self.location or '').strip()

        if not self.asset_name:
            raise ValidationError({'asset_name': 'Asset name is required.'})
        if not self.asset_code:
            raise ValidationError({'asset_code': 'Asset code is required.'})
        if not self.category:
            raise ValidationError({'category': 'Category is required.'})
        if self.purchase_cost is None or self.purchase_cost < 0:
            raise ValidationError({'purchase_cost': 'Purchase cost cannot be negative.'})

        if self.assigned_to_id and self.assigned_to.school_id != self.school_id:
            raise ValidationError({'assigned_to': 'Assigned staff must belong to selected school.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active', 'updated_at'])

    def __str__(self):
        return f"{self.asset_code} - {self.asset_name}"


class StockItem(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='stock_items_core',
    )
    objects = SchoolManager()

    item_name = models.CharField(max_length=150)
    item_code = models.CharField(max_length=60)
    category = models.CharField(max_length=120)
    quantity_available = models.PositiveIntegerField(default=0)
    minimum_threshold = models.PositiveIntegerField(default=0)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['item_name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'item_code'],
                name='unique_stock_item_code_per_school',
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gte=0),
                name='stock_item_unit_price_non_negative',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'category']),
            models.Index(fields=['school', 'minimum_threshold']),
        ]

    @property
    def is_low_stock(self):
        return self.quantity_available < self.minimum_threshold

    def clean(self):
        super().clean()
        self.item_name = (self.item_name or '').strip()
        self.item_code = (self.item_code or '').strip().upper()
        self.category = (self.category or '').strip()

        if not self.item_name:
            raise ValidationError({'item_name': 'Item name is required.'})
        if not self.item_code:
            raise ValidationError({'item_code': 'Item code is required.'})
        if not self.category:
            raise ValidationError({'category': 'Category is required.'})
        if self.unit_price is None or self.unit_price < 0:
            raise ValidationError({'unit_price': 'Unit price cannot be negative.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active', 'updated_at'])

    def __str__(self):
        return f"{self.item_code} - {self.item_name}"


class Vendor(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='vendors_core',
    )
    objects = SchoolManager()

    vendor_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    gst_number = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['vendor_name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'vendor_name'],
                name='unique_vendor_name_per_school',
            ),
            models.UniqueConstraint(
                fields=['school', 'gst_number'],
                condition=~Q(gst_number=''),
                name='unique_vendor_gst_per_school',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_active']),
        ]

    def clean(self):
        super().clean()
        self.vendor_name = (self.vendor_name or '').strip()
        self.gst_number = (self.gst_number or '').strip().upper()
        if not self.vendor_name:
            raise ValidationError({'vendor_name': 'Vendor name is required.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active', 'updated_at'])

    def __str__(self):
        return self.vendor_name


class Purchase(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='purchases_core',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='purchases_core',
    )
    objects = SchoolManager()

    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.PROTECT,
        related_name='purchases',
    )
    purchase_date = models.DateField(default=timezone.localdate)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    invoice_number = models.CharField(max_length=120)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_purchases_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-purchase_date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'session', 'invoice_number'],
                name='unique_purchase_invoice_per_session',
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gte=0),
                name='purchase_total_non_negative',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'purchase_date']),
            models.Index(fields=['school', 'vendor']),
        ]

    def clean(self):
        super().clean()
        self.invoice_number = (self.invoice_number or '').strip()

        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})
        if self.vendor_id and self.vendor.school_id != self.school_id:
            raise ValidationError({'vendor': 'Vendor must belong to selected school.'})
        if not self.invoice_number:
            raise ValidationError({'invoice_number': 'Invoice number is required.'})
        if self.total_amount is None or self.total_amount < 0:
            raise ValidationError({'total_amount': 'Total amount cannot be negative.'})

    def delete(self, *args, **kwargs):
        raise ValidationError('Purchase records cannot be deleted.')

    def __str__(self):
        return f"{self.invoice_number} ({self.purchase_date})"


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(
        Purchase,
        on_delete=models.CASCADE,
        related_name='items',
    )
    stock_item = models.ForeignKey(
        StockItem,
        on_delete=models.PROTECT,
        related_name='purchase_items',
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name='purchase_item_quantity_positive',
            ),
            models.CheckConstraint(
                condition=Q(unit_price__gt=0),
                name='purchase_item_unit_price_positive',
            ),
            models.CheckConstraint(
                condition=Q(line_total__gte=0),
                name='purchase_item_line_total_non_negative',
            ),
        ]
        indexes = [
            models.Index(fields=['purchase', 'stock_item']),
        ]

    def clean(self):
        super().clean()
        if self.stock_item_id and self.purchase_id and self.stock_item.school_id != self.purchase.school_id:
            raise ValidationError({'stock_item': 'Stock item must belong to purchase school.'})
        if self.quantity is None or self.quantity <= 0:
            raise ValidationError({'quantity': 'Quantity must be greater than zero.'})
        if self.unit_price is None or self.unit_price <= 0:
            raise ValidationError({'unit_price': 'Unit price must be greater than zero.'})

    def save(self, *args, **kwargs):
        self.line_total = Decimal(self.quantity) * Decimal(self.unit_price)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Purchase items cannot be deleted.')

    def __str__(self):
        return f"{self.purchase.invoice_number} - {self.stock_item.item_name}"


class Book(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='books_core',
    )
    objects = SchoolManager()

    title = models.CharField(max_length=200)
    author = models.CharField(max_length=150, blank=True)
    isbn = models.CharField(max_length=30, blank=True)
    category = models.CharField(max_length=120, blank=True)
    total_copies = models.PositiveIntegerField(default=1)
    available_copies = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['school', 'isbn'],
                condition=~Q(isbn=''),
                name='unique_book_isbn_per_school',
            ),
            models.CheckConstraint(
                condition=Q(total_copies__gt=0),
                name='book_total_copies_positive',
            ),
            models.CheckConstraint(
                condition=Q(available_copies__gte=0) & Q(available_copies__lte=F('total_copies')),
                name='book_available_within_total',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'is_active']),
            models.Index(fields=['school', 'category']),
        ]

    def clean(self):
        super().clean()
        self.title = (self.title or '').strip()
        self.author = (self.author or '').strip()
        self.isbn = (self.isbn or '').strip().upper()
        self.category = (self.category or '').strip()

        if not self.title:
            raise ValidationError({'title': 'Book title is required.'})
        if not self.total_copies or self.total_copies <= 0:
            raise ValidationError({'total_copies': 'Total copies must be greater than zero.'})
        if self.available_copies > self.total_copies:
            raise ValidationError({'available_copies': 'Available copies cannot exceed total copies.'})

    def delete(self, *args, **kwargs):
        if self.is_active:
            self.is_active = False
            self.save(update_fields=['is_active', 'updated_at'])

    def __str__(self):
        return self.title


class BookIssue(models.Model):
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name='book_issues_core',
    )
    session = models.ForeignKey(
        AcademicSession,
        on_delete=models.CASCADE,
        related_name='book_issues_core',
    )
    objects = SchoolManager()

    book = models.ForeignKey(
        Book,
        on_delete=models.PROTECT,
        related_name='issues',
    )
    issued_student = models.ForeignKey(
        Student,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='book_issues',
    )
    issued_staff = models.ForeignKey(
        Staff,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='book_issues',
    )
    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    return_date = models.DateField(null=True, blank=True)
    fine_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='book_issues_created',
    )
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='book_issues_returned',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-issue_date', '-id']
        constraints = [
            models.CheckConstraint(
                condition=(
                    (Q(issued_student__isnull=False) & Q(issued_staff__isnull=True))
                    | (Q(issued_student__isnull=True) & Q(issued_staff__isnull=False))
                ),
                name='book_issue_exactly_one_recipient',
            ),
            models.CheckConstraint(
                condition=Q(fine_amount__gte=0),
                name='book_issue_fine_non_negative',
            ),
        ]
        indexes = [
            models.Index(fields=['school', 'session', 'is_active']),
            models.Index(fields=['school', 'due_date']),
            models.Index(fields=['school', 'return_date']),
        ]

    @property
    def issued_to_display(self):
        if self.issued_student_id:
            return self.issued_student.full_name
        if self.issued_staff_id:
            return self.issued_staff.user.get_full_name() or self.issued_staff.employee_id
        return '-'

    def clean(self):
        super().clean()
        if self.session_id and self.session.school_id != self.school_id:
            raise ValidationError({'session': 'Session must belong to selected school.'})
        if self.book_id and self.book.school_id != self.school_id:
            raise ValidationError({'book': 'Book must belong to selected school.'})

        if self.issued_student_id:
            if self.issued_student.school_id != self.school_id:
                raise ValidationError({'issued_student': 'Student must belong to selected school.'})
            if self.issued_student.session_id != self.session_id:
                raise ValidationError({'issued_student': 'Student must belong to selected session.'})
        if self.issued_staff_id and self.issued_staff.school_id != self.school_id:
            raise ValidationError({'issued_staff': 'Staff must belong to selected school.'})

        if self.due_date and self.issue_date and self.due_date < self.issue_date:
            raise ValidationError({'due_date': 'Due date cannot be before issue date.'})
        if self.return_date and self.return_date < self.issue_date:
            raise ValidationError({'return_date': 'Return date cannot be before issue date.'})

    def delete(self, *args, **kwargs):
        raise ValidationError('Book issue records cannot be deleted.')

    def __str__(self):
        return f"{self.book.title} - {self.issued_to_display}"
