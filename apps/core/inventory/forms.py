from datetime import timedelta

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.academic_sessions.models import AcademicSession
from apps.core.hr.models import Staff
from apps.core.students.models import Student

from .models import Asset, Book, BookIssue, StockItem, Vendor


def _school_sessions(school):
    return AcademicSession.objects.filter(school=school).order_by('-start_date')


class AssetForm(forms.ModelForm):
    class Meta:
        model = Asset
        fields = [
            'asset_name',
            'asset_code',
            'category',
            'purchase_date',
            'purchase_cost',
            'location',
            'condition',
            'assigned_to',
            'is_active',
        ]
        widgets = {
            'purchase_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = Staff.objects.none()
        if self.school:
            self.fields['assigned_to'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('employee_id')


class StockItemForm(forms.ModelForm):
    class Meta:
        model = StockItem
        fields = [
            'item_name',
            'item_code',
            'category',
            'quantity_available',
            'minimum_threshold',
            'unit_price',
            'is_active',
        ]


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            'vendor_name',
            'phone',
            'email',
            'address',
            'gst_number',
            'is_active',
        ]


class PurchaseEntryForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    vendor = forms.ModelChoiceField(queryset=Vendor.objects.none())
    purchase_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    invoice_number = forms.CharField(max_length=120)
    stock_item = forms.ModelChoiceField(queryset=StockItem.objects.none())
    quantity = forms.IntegerField(min_value=1)
    unit_price = forms.DecimalField(max_digits=12, decimal_places=2, min_value=0.01)

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['vendor'].queryset = Vendor.objects.none()
        self.fields['stock_item'].queryset = StockItem.objects.none()

        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)
            self.fields['vendor'].queryset = Vendor.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('vendor_name')
            self.fields['stock_item'].queryset = StockItem.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('item_name')

        if self.default_session and not self.is_bound:
            self.initial.setdefault('session', self.default_session.id)
        if not self.is_bound:
            self.initial.setdefault('purchase_date', timezone.localdate())


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = [
            'title',
            'author',
            'isbn',
            'category',
            'total_copies',
            'available_copies',
            'is_active',
        ]


class BookIssueForm(forms.Form):
    session = forms.ModelChoiceField(queryset=AcademicSession.objects.none())
    book = forms.ModelChoiceField(queryset=Book.objects.none())
    issued_student = forms.ModelChoiceField(queryset=Student.objects.none(), required=False)
    issued_staff = forms.ModelChoiceField(queryset=Staff.objects.none(), required=False)
    issue_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    due_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))

    def __init__(self, *args, **kwargs):
        self.school = kwargs.pop('school', None)
        self.default_session = kwargs.pop('default_session', None)
        super().__init__(*args, **kwargs)

        self.fields['session'].queryset = AcademicSession.objects.none()
        self.fields['book'].queryset = Book.objects.none()
        self.fields['issued_student'].queryset = Student.objects.none()
        self.fields['issued_staff'].queryset = Staff.objects.none()

        selected_session_id = None
        if self.is_bound:
            selected_session_id = self.data.get('session')
        elif self.default_session:
            selected_session_id = self.default_session.id
            self.initial.setdefault('session', self.default_session.id)

        if self.school:
            self.fields['session'].queryset = _school_sessions(self.school)
            self.fields['book'].queryset = Book.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('title')
            students = Student.objects.filter(
                school=self.school,
                is_active=True,
                is_archived=False,
            ).order_by('admission_number')
            if selected_session_id:
                students = students.filter(session_id=selected_session_id)
            self.fields['issued_student'].queryset = students
            self.fields['issued_staff'].queryset = Staff.objects.filter(
                school=self.school,
                is_active=True,
            ).order_by('employee_id')

        if not self.is_bound:
            today = timezone.localdate()
            self.initial.setdefault('issue_date', today)
            self.initial.setdefault('due_date', today + timedelta(days=14))

    def clean(self):
        cleaned = super().clean()
        has_student = cleaned.get('issued_student') is not None
        has_staff = cleaned.get('issued_staff') is not None
        if has_student == has_staff:
            raise ValidationError('Select either student or staff as recipient.')
        return cleaned


class BookReturnForm(forms.Form):
    return_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    fine_per_day = forms.DecimalField(max_digits=10, decimal_places=2, min_value=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.setdefault('return_date', timezone.localdate())
            self.initial.setdefault('fine_per_day', getattr(settings, 'LIBRARY_FINE_PER_DAY', 5))
