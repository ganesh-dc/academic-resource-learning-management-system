# myapp/decorators.py
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect
from django.contrib import messages

def admin_required(function=None):
    """
    Decorator for views that checks that the user is an admin or staff,
    redirecting to the login page if necessary.
    """
    def is_admin_user(user):
        return user.is_authenticated and (user.role == 'admin' or user.is_staff)
    
    actual_decorator = user_passes_test(
        is_admin_user,
        login_url='login',
        redirect_field_name=None
    )
    
    if function:
        return actual_decorator(function)
    return actual_decorator

def student_required(function=None):
    """
    Decorator for views that checks that the user is a student.
    """
    def is_student_user(user):
        return user.is_authenticated and user.role == 'student'
    
    actual_decorator = user_passes_test(
        is_student_user,
        login_url='login',
        redirect_field_name=None
    )
    
    if function:
        return actual_decorator(function)
    return actual_decorator

def teacher_required(function=None):
    """
    Decorator for views that checks that the user is a teacher.
    """
    def is_teacher_user(user):
        return user.is_authenticated and user.role == 'teacher'
    
    actual_decorator = user_passes_test(
        is_teacher_user,
        login_url='login',
        redirect_field_name=None
    )
    
    if function:
        return actual_decorator(function)
    return actual_decorator

def role_required(allowed_roles):
    """
    Decorator that checks if user has one of the allowed roles.
    Usage: @role_required(['admin', 'teacher'])
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            if request.user.is_authenticated and request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            messages.error(request, "You don't have permission to access this page.")
            return redirect('dashboard')
        return wrapper
    return decorator