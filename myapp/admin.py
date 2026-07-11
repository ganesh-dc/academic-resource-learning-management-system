
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Category, Resource, Payment, Feedback, Notification

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'is_staff', 'phone', 'created_at')
    list_filter = ('role', 'is_staff', 'is_superuser')
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('role', 'phone', 'student_id', 'full_name', 'program', 'semester', 'section', 'address')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Additional Info', {'fields': ('role', 'phone')}),
    )

admin.site.register(User, CustomUserAdmin)
admin.site.register(Category)
admin.site.register(Resource)
admin.site.register(Payment)
admin.site.register(Feedback)
admin.site.register(Notification)