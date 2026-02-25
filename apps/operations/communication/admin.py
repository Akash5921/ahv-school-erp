from django.contrib import admin

from .models import Notice, NoticeRead


admin.site.register(Notice)
admin.site.register(NoticeRead)
