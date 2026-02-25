from django import forms

from .models import Notice


class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ['title', 'message', 'target_role', 'priority', 'is_published', 'publish_at']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 4}),
            'publish_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
