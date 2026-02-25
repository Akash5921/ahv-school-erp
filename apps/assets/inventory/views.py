from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.core.users.audit import log_audit_event
from apps.core.users.decorators import role_required

from .forms import InventoryCategoryForm, InventoryItemForm, InventoryPurchaseForm
from .models import InventoryCategory, InventoryItem, InventoryPurchase


@login_required
@role_required('schooladmin')
def category_list(request):
    school = request.user.school
    categories = InventoryCategory.objects.all().order_by('name')
    error = None

    if request.method == 'POST':
        form = InventoryCategoryForm(request.POST)
        if form.is_valid():
            name = form.cleaned_data['name'].strip()
            if not name:
                error = 'Category name is required.'
            else:
                category, _ = InventoryCategory.objects.get_or_create(name=name)
                log_audit_event(
                    request=request,
                    action='inventory.category_saved',
                    school=school,
                    target=category,
                    details=f"Name={category.name}",
                )
                return redirect('inventory_category_list')
    else:
        form = InventoryCategoryForm()

    return render(request, 'inventory/category_list.html', {
        'categories': categories,
        'form': form,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def item_list(request):
    school = request.user.school
    items = InventoryItem.objects.filter(
        school=school
    ).select_related('category').order_by('name')
    error = None

    if request.method == 'POST':
        form = InventoryItemForm(request.POST)
        form.fields['category'].queryset = InventoryCategory.objects.all().order_by('name')
        if form.is_valid():
            item = form.save(commit=False)
            item.school = school
            item.save()
            log_audit_event(
                request=request,
                action='inventory.item_created',
                school=school,
                target=item,
                details=f"Name={item.name}, Quantity={item.quantity}",
            )
            return redirect('inventory_item_list')
        error = 'Please correct the item details.'
    else:
        form = InventoryItemForm()
        form.fields['category'].queryset = InventoryCategory.objects.all().order_by('name')

    return render(request, 'inventory/item_list.html', {
        'items': items,
        'form': form,
        'error': error,
    })


@login_required
@role_required('schooladmin')
def purchase_item(request):
    school = request.user.school
    current_session = school.current_session
    error = None

    school_items = InventoryItem.objects.filter(school=school).order_by('name')
    purchases = InventoryPurchase.objects.filter(
        item__school=school,
        academic_session=current_session
    ).select_related('item').order_by('-purchase_date', '-id') if current_session else []

    if request.method == 'POST':
        form = InventoryPurchaseForm(request.POST)
        form.fields['item'].queryset = school_items

        if not current_session:
            error = 'No active academic session set for this school.'
        elif form.is_valid():
            purchase = form.save(commit=False)
            purchase.academic_session = current_session
            purchase.save()

            log_audit_event(
                request=request,
                action='inventory.purchase_recorded',
                school=school,
                target=purchase,
                details=f"Item={purchase.item_id}, Qty={purchase.quantity_purchased}, Cost={purchase.total_cost}",
            )
            return redirect('inventory_purchase')
        else:
            error = 'Please correct purchase details.'
    else:
        form = InventoryPurchaseForm()
        form.fields['item'].queryset = school_items

    return render(request, 'inventory/purchase_item.html', {
        'form': form,
        'purchases': purchases,
        'error': error,
        'current_session': current_session,
    })
