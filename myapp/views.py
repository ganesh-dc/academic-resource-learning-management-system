import random
import string
import time
import os
import json
import uuid
import csv
import re
from datetime import datetime, timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils import timezone
from django.http import FileResponse, HttpResponse, JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Avg, Count
from django.db import transaction
from django.core.cache import cache
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import Group

# Import your custom User model
User = get_user_model()

# Import your models
from .models import User, Resource, Category, Payment, Feedback, Notification, OTPStorage, RegistrationAttempt, VerificationLog
from .forms import ResourceUploadForm, CategoryForm, TeacherCreationForm

# ========== ROLE-BASED DECORATORS ==========
def admin_required(view_func):
    """Decorator for admin-only views"""
    return user_passes_test(lambda u: u.is_authenticated and u.role == 'admin')(view_func)

def teacher_required(view_func):
    """Decorator for teacher-only views"""
    return user_passes_test(lambda u: u.is_authenticated and u.role == 'teacher')(view_func)

def student_required(view_func):
    """Decorator for student-only views"""
    return user_passes_test(lambda u: u.is_authenticated and u.role == 'student')(view_func)
# ===========================================

def home(request):
    """Home page view with statistics"""
    from django.db.models import Count
    
    # Get statistics - Use get_user_model() directly
    total_resources = Resource.objects.count()
    active_students = User.objects.filter(role='student', is_active=True).count()
    teachers = User.objects.filter(role='teacher', is_active=True).count()
    courses = Category.objects.count()
    
    # Get programs with resource counts
    programs_data = []
    program_choices = User.PROGRAM_CHOICES
    
    for code, name in program_choices:
        if code != 'other':
            # Count resources for this program
            resource_count = Resource.objects.filter(
                Q(uploaded_by__program=code) |
                Q(title__icontains=name.split('(')[0])
            ).distinct().count()
            
            # Get thumbnail resources for this program
            program_resources = Resource.objects.filter(
                Q(uploaded_by__program=code) |
                Q(title__icontains=name.split('(')[0])
            )[:3]
            
            programs_data.append({
                'code': code,
                'name': name,
                'resource_count': resource_count,
                'resources': program_resources,
            })
    
    context = {
        'stats': {
            'total_resources': total_resources,
            'active_students': active_students,
            'teachers': teachers,
            'courses': courses,
        },
        'programs': programs_data,
    }
    return render(request, 'myapp/home.html', context)

@login_required
def dashboard(request):
    """Universal dashboard - redirects based on user type"""
    user = request.user
    
    # Debug print
    print(f"\n=== DASHBOARD REDIRECT ===")
    print(f"User: {user.username}")
    print(f"Role: {getattr(user, 'role', 'NO ROLE ATTRIBUTE')}")
    
    # Safety check for Django superuser
    if user.is_superuser:
        print("Redirecting Django superuser to Django admin")
        return redirect('/admin/')
    
    # Check user role and redirect accordingly
    if hasattr(user, 'role'):
        if user.role == 'admin':
            print("Redirecting to admin_dashboard")
            return redirect('admin_dashboard')
        elif user.role == 'teacher':
            print("Redirecting to teacher_dashboard")
            return redirect('teacher_dashboard')
        elif user.role == 'student':
            print("Redirecting to student_dashboard")
            return redirect('student_dashboard')
    
    # Default fallback
    print("Redirecting to home (fallback)")
    return redirect('home')

# ========== REGISTRATION AND OTP VIEWS ==========

# Simple in-memory storage for OTPs (for testing only)
otp_storage = {}

def generate_otp(length=6):
    """Generate a random 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=length))

@csrf_exempt
def send_otp(request):
    """Handle OTP sending via AJAX"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            email = data.get('email')
            
            if not email:
                return JsonResponse({'success': False, 'error': 'Email is required'})
            
            # Generate OTP
            otp = generate_otp()
            
            # Store OTP with timestamp
            otp_storage[email] = {
                'otp': otp,
                'timestamp': time.time(),
                'verified': False
            }
            
            # For testing: Print OTP to terminal
            print("\n" + "="*50)
            print("OTP FOR TESTING:")
            print(f"Email: {email}")
            print(f"OTP: {otp}")
            print("="*50 + "\n")
            
            return JsonResponse({
                'success': True, 
                'message': 'OTP sent successfully',
                'otp': otp  # Sending OTP back for testing
            })
            
        except Exception as e:
            print(f"Error sending OTP: {e}")
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def register_view(request):
    """Handle student registration with OTP verification"""
    if request.method == 'POST':
        # Extract form data
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        student_id = request.POST.get('student_id', '').strip()
        full_name = request.POST.get('full_name', '').strip()
        program = request.POST.get('program', '')
        semester = request.POST.get('semester', '')
        shift = request.POST.get('shift', '')
        phone = request.POST.get('phone', '').strip()
        address = request.POST.get('address', '').strip()
        agree_terms = request.POST.get('agreeTerms')
        otp_verified = request.POST.get('otp_verified')
        
        # Store form data for re-display
        form_data = {
            'username': username,
            'email': email,
            'password1': password1,
            'password2': password2,
            'student_id': student_id,
            'full_name': full_name,
            'program': program,
            'semester': semester,
            'shift': shift,
            'phone': phone,
            'address': address,
            'agreeTerms': agree_terms,
        }
        
        errors = {}
        
        # Check OTP verification
        if otp_verified != '1':
            errors['otp'] = 'Please verify your email with OTP first'
        
        # Validate username
        if not username:
            errors['username'] = 'Username is required'
        elif len(username) < 4 or len(username) > 30:
            errors['username'] = 'Username must be 4-30 characters'
        elif User.objects.filter(username=username).exists():
            errors['username'] = 'Username already exists'
        
        # Validate email
        if not email:
            errors['email'] = 'Email is required'
        elif not '@' in email or not '.' in email:
            errors['email'] = 'Enter a valid email address'
        elif User.objects.filter(email=email).exists():
            errors['email'] = 'Email already registered'
        
        # Validate passwords
        if not password1:
            errors['password1'] = 'Password is required'
        elif len(password1) < 8:
            errors['password1'] = 'Password must be at least 8 characters'
        
        if not password2:
            errors['password2'] = 'Confirm password is required'
        elif password1 != password2:
            errors['password2'] = 'Passwords do not match'
        
        # Validate other fields
        if not student_id:
            errors['student_id'] = 'Student ID is required'
        
        if not full_name:
            errors['full_name'] = 'Full name is required'
        
        if not program:
            errors['program'] = 'Program is required'
        
        if not semester:
            errors['semester'] = 'Semester is required'
        
        if not shift:
            errors['shift'] = 'Shift is required'
        
        if not phone:
            errors['phone'] = 'Phone number is required'
        elif not phone.isdigit() or len(phone) != 10:
            errors['phone'] = 'Enter valid 10-digit phone number'
        
        if not agree_terms:
            errors['terms'] = 'You must agree to the terms and conditions'
        
        # If no errors, create user
        if not errors:
            try:
                # Create user with your custom User model
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password1
                )
                user.first_name = full_name
                user.role = 'student'
                user.student_id = student_id
                user.full_name = full_name
                user.program = program
                user.semester = semester
                user.shift = shift
                user.phone = phone
                user.address = address
                user.is_email_verified = True  # Since OTP is verified
                user.verification_status = 'verified'
                user.save()
                
                messages.success(request, f'Registration successful! Welcome {full_name}')
                
                # Clear OTP from storage
                if email in otp_storage:
                    del otp_storage[email]
                
                # Auto login after registration
                user = authenticate(request, username=username, password=password1)
                if user is not None:
                    login(request, user)
                    messages.success(request, f'Welcome to ARLMS, {full_name}!')
                    return redirect('student_dashboard')
                else:
                    return redirect('login')
                
            except Exception as e:
                errors['general'] = f'Registration failed: {str(e)}'
                print(f"Registration error: {e}")
        
        # If there are errors, re-render form with error messages
        return render(request, 'myapp/register.html', {
            'errors': errors,
            'form_data': form_data
        })
    
    # GET request - show empty form
    return render(request, 'myapp/register.html')

@csrf_exempt
def verify_otp(request):
    """Verify OTP via AJAX"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            email = data.get('email')
            otp = data.get('otp')
            
            if not email or not otp:
                return JsonResponse({'success': False, 'error': 'Email and OTP required'})
            
            # Check if OTP exists and is valid
            if email in otp_storage:
                stored_data = otp_storage[email]
                
                # Check if OTP matches
                if stored_data['otp'] == otp:
                    # Check if OTP is expired (5 minutes)
                    if time.time() - stored_data['timestamp'] > 300:
                        return JsonResponse({'success': False, 'error': 'OTP expired'})
                    
                    # Mark as verified
                    otp_storage[email]['verified'] = True
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'OTP verified successfully'
                    })
            
            return JsonResponse({'success': False, 'error': 'Invalid OTP'})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def check_otp_status(request):
    """Check if OTP is verified for an email"""
    if request.method == 'GET':
        email = request.GET.get('email')
        
        if email and email in otp_storage:
            return JsonResponse({
                'verified': otp_storage[email]['verified']
            })
        
        return JsonResponse({'verified': False})
    
    return JsonResponse({'verified': False})

# ========== LOGIN/LOGOUT VIEWS ==========

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            
            # Add welcome message
            messages.success(request, f'Welcome back, {user.username}!')
            
            print(f"\n=== LOGIN DEBUG ===")
            print(f"Username: {user.username}")
            print(f"Role: {user.role}")
            print(f"Is superuser: {user.is_superuser}")
            
            # Check if user is Django superuser
            if user.is_superuser:
                print("REDIRECT: Django admin (superuser)")
                return redirect('/admin/')
            
            # Simple redirect - dashboard will handle role-based routing
            print("REDIRECT: Universal dashboard")
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
            return render(request, 'myapp/login.html', {'username': username})
    
    return render(request, 'myapp/login.html')

def logout_view(request):
    logout(request)
    return redirect('login')

# ========== PASSWORD RESET VIEWS ==========

def forgot_password_view(request):
    """Step 1: User enters email to get OTP"""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        
        if not email:
            messages.error(request, 'Email is required')
            return render(request, 'myapp/forgot_password.html')
        
        # Check if email exists in system
        try:
            user = User.objects.get(email=email)
            
            # Generate 6-digit OTP
            otp = ''.join(random.choices(string.digits, k=6))
            
            # Store OTP in cache (valid for 10 minutes)
            cache_key = f'reset_otp_{email}'
            cache.set(cache_key, {
                'otp': otp,
                'email': email,
                'user_id': user.id,
                'attempts': 0
            }, 600)  # 10 minutes
            
            # For testing, print OTP to console
            print(f"\n{'='*60}")
            print(f"🔐 PASSWORD RESET OTP for {email}: {otp}")
            print(f"📝 Enter this OTP in the password reset form")
            print(f"{'='*60}\n")
            
            # Store email in session for next step
            request.session['reset_email'] = email
            request.session['reset_step'] = 'otp_sent'
            
            messages.success(request, f'OTP has been sent to {email}. Check the Django terminal for OTP.')
            return redirect('verify_reset_otp')
            
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email')
    
    return render(request, 'myapp/forgot_password.html')

def verify_reset_otp(request):
    """Step 2: User verifies OTP"""
    reset_email = request.session.get('reset_email')
    
    if not reset_email:
        messages.error(request, 'Please enter your email first')
        return redirect('forgot_password')
    
    if request.method == 'POST':
        otp = request.POST.get('otp', '').strip()
        
        if not otp or len(otp) != 6:
            messages.error(request, 'Please enter a valid 6-digit OTP')
            return render(request, 'myapp/verify_reset_otp.html')
        
        # Get OTP from cache
        cache_key = f'reset_otp_{reset_email}'
        otp_data = cache.get(cache_key)
        
        if not otp_data:
            messages.error(request, 'OTP expired or not found. Please request a new one.')
            return redirect('forgot_password')
        
        # Check OTP
        if otp_data['otp'] != otp:
            otp_data['attempts'] += 1
            cache.set(cache_key, otp_data, 600)
            
            if otp_data['attempts'] >= 3:
                cache.delete(cache_key)
                messages.error(request, 'Too many failed attempts. OTP invalidated.')
                return redirect('forgot_password')
            
            messages.error(request, 'Invalid OTP. Please try again.')
            return render(request, 'myapp/verify_reset_otp.html')
        
        # OTP verified successfully
        request.session['reset_step'] = 'otp_verified'
        request.session['reset_user_id'] = otp_data['user_id']
        
        # Clear OTP from cache
        cache.delete(cache_key)
        
        messages.success(request, 'OTP verified successfully! You can now reset your password.')
        return redirect('reset_password')
    
    return render(request, 'myapp/verify_reset_otp.html', {'email': reset_email})

def reset_password_view(request):
    """Step 3: User sets new password"""
    if request.session.get('reset_step') != 'otp_verified':
        messages.error(request, 'Please verify OTP first')
        return redirect('forgot_password')
    
    user_id = request.session.get('reset_user_id')
    
    if not user_id:
        messages.error(request, 'Session expired. Please start over.')
        return redirect('forgot_password')
    
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        messages.error(request, 'User not found')
        return redirect('forgot_password')
    
    if request.method == 'POST':
        password1 = request.POST.get('password1', '')
        password2 = request.POST.get('password2', '')
        
        if not password1 or not password2:
            messages.error(request, 'Both password fields are required')
            return render(request, 'myapp/reset_password.html')
        
        if password1 != password2:
            messages.error(request, 'Passwords do not match')
            return render(request, 'myapp/reset_password.html')
        
        if len(password1) < 8:
            messages.error(request, 'Password must be at least 8 characters')
            return render(request, 'myapp/reset_password.html')
        
        # Update password
        user.set_password(password1)
        user.save()
        
        # Clear session
        request.session.pop('reset_email', None)
        request.session.pop('reset_step', None)
        request.session.pop('reset_user_id', None)
        
        messages.success(request, 'Password reset successfully! You can now login with your new password.')
        return redirect('reset_password_success')
    
    return render(request, 'myapp/reset_password.html', {'email': user.email})

def reset_password_success(request):
    """Step 4: Success page"""
    return render(request, 'myapp/reset_password_success.html')

# ========== DASHBOARD VIEWS ==========

@login_required
@admin_required
def admin_dashboard(request):
    """Admin Dashboard"""
    # Get statistics using your custom User model
    total_users = User.objects.count()
    student_count = User.objects.filter(role='student', is_active=True).count()
    teacher_count = User.objects.filter(role='teacher', is_active=True).count()
    admin_count = User.objects.filter(role='admin', is_active=True).count()
    total_resources = Resource.objects.count()
    premium_resources = Resource.objects.filter(is_premium=True).count()
    free_resources = Resource.objects.filter(is_premium=False).count()
    
    # Payment statistics
    total_payments = Payment.objects.count()
    total_revenue_result = Payment.objects.filter(status='completed').aggregate(total=Sum('amount'))
    total_revenue = total_revenue_result['total'] or 0.00
    
    # Today's statistics
    today = timezone.now().date()
    today_users = User.objects.filter(date_joined__date=today).count()
    today_resources = Resource.objects.filter(uploaded_date__date=today).count()
    today_payments = Payment.objects.filter(payment_date__date=today, status='completed').count()
    today_revenue_result = Payment.objects.filter(payment_date__date=today, status='completed').aggregate(total=Sum('amount'))
    today_revenue = today_revenue_result['total'] or 0.00
    
    # Weekly users
    week_ago = today - timedelta(days=7)
    week_users = User.objects.filter(date_joined__date__gte=week_ago).count()
    
    context = {
        'total_users': total_users,
        'student_count': student_count,
        'teacher_count': teacher_count,
        'admin_count': admin_count,
        'total_resources': total_resources,
        'premium_resources': premium_resources,
        'free_resources': free_resources,
        'total_revenue': total_revenue,
        'today_revenue': today_revenue,
        'today_users': today_users,
        'today_resources': today_resources,
        'today_payments': today_payments,
        'week_users': week_users,
        'total_payments': total_payments,
        'payment_total_revenue': total_revenue,
    }
    
    return render(request, 'myapp/admin_dashboard.html', context)

@login_required
@teacher_required
def teacher_dashboard(request):
    """Teacher Dashboard View"""
    try:
        # Get teacher's resources
        my_resources = Resource.objects.filter(uploaded_by=request.user).order_by('-uploaded_date')
        
        # Get notifications
        recent_notifications = Notification.objects.filter(receiver=request.user).order_by('-created_at')[:10]
        
        # Get feedback on teacher's resources
        resource_feedbacks = Feedback.objects.filter(resource__uploaded_by=request.user).order_by('-created_at')[:10]
        
        # Calculate stats
        resource_count = my_resources.count()
        
        # Calculate total downloads
        total_downloads = 0
        for resource in my_resources:
            download_count = getattr(resource, 'download_count', None)
            if download_count is not None:
                total_downloads += download_count
        
        # Count unread notifications
        unread_count = Notification.objects.filter(receiver=request.user, is_read=False).count()
        
        # Calculate average rating
        avg_rating = None
        all_feedbacks = Feedback.objects.filter(resource__uploaded_by=request.user)
        if all_feedbacks.exists():
            total_rating = 0
            count = 0
            for feedback in all_feedbacks:
                if hasattr(feedback, 'rating'):
                    total_rating += feedback.rating
                    count += 1
            if count > 0:
                avg_rating = total_rating / count
        
        # Count premium and free resources
        premium_count = my_resources.filter(is_premium=True).count()
        free_count = my_resources.filter(is_premium=False).count()
        
        context = {
            'my_resources': my_resources,
            'recent_notifications': recent_notifications,
            'resource_feedbacks': resource_feedbacks,
            'resource_count': resource_count,
            'total_downloads': total_downloads,
            'unread_count': unread_count,
            'premium_count': premium_count,
            'free_count': free_count,
            'avg_rating': avg_rating,
        }
        
        return render(request, 'myapp/teacher_dashboard.html', context)
        
    except Exception as e:
        print(f"Error in teacher_dashboard: {e}")
        return render(request, 'myapp/teacher_dashboard.html', {
            'my_resources': [],
            'recent_notifications': [],
            'resource_feedbacks': [],
            'resource_count': 0,
            'total_downloads': 0,
            'unread_count': 0,
            'premium_count': 0,
            'free_count': 0,
            'avg_rating': None,
        })

@login_required
@student_required
def student_dashboard(request):
    """Student dashboard view"""
    recent_resources = Resource.objects.all().order_by('-uploaded_date')[:10]
    
    purchased_payments = Payment.objects.filter(
        student=request.user, 
        status='completed'
    )
    purchased_resource_ids = purchased_payments.values_list('resource_id', flat=True)
    
    student_notifications = Notification.objects.filter(
        receiver=request.user
    ).order_by('-created_at')[:5]
    
    context = {
        'recent_resources': recent_resources,
        'purchased_resource_ids': list(purchased_resource_ids),
        'student_notifications': student_notifications,
        'user': request.user,
    }
    return render(request, 'myapp/student_dashboard.html', context)

# ========== RESOURCE VIEWS ==========

def resource_list(request):
    """List all resources with optional filtering"""
    category_id = request.GET.get('category')
    search_query = request.GET.get('search')
    resource_type = request.GET.get('type', '')
    sort_by = request.GET.get('sort', 'newest')
    program_filter = request.GET.get('program', '')
    
    resources = Resource.objects.all()
    
    if category_id:
        resources = resources.filter(category_id=category_id)
    
    if program_filter:
        resources = resources.filter(uploaded_by__program=program_filter)
    
    if resource_type == 'free':
        resources = resources.filter(is_premium=False)
    elif resource_type == 'premium':
        resources = resources.filter(is_premium=True)
    
    if search_query:
        resources = resources.filter(
            Q(title__icontains=search_query) | 
            Q(description__icontains=search_query)
        )
    
    if sort_by == 'newest':
        resources = resources.order_by('-uploaded_date')
    elif sort_by == 'oldest':
        resources = resources.order_by('uploaded_date')
    elif sort_by == 'views':
        resources = resources.order_by('-views')
    elif sort_by == 'title':
        resources = resources.order_by('title')
    
    free_count = resources.filter(is_premium=False).count()
    premium_count = resources.filter(is_premium=True).count()
    
    categories = Category.objects.all()
    
    context = {
        'resources': resources,
        'categories': categories,
        'selected_category': category_id,
        'search_query': search_query or '',
        'free_count': free_count,
        'premium_count': premium_count,
        'program_filter': program_filter,
    }
    
    return render(request, 'myapp/resource_list.html', context)

@login_required
def resource_detail(request, resource_id):
    """View individual resource details"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    resource.views += 1
    resource.save()
    
    feedbacks = Feedback.objects.filter(resource=resource).order_by('-created_at')
    
    # Calculate average rating
    avg_rating = 0
    if feedbacks.exists():
        avg_rating_result = feedbacks.aggregate(Avg('rating'))
        avg_rating = avg_rating_result['rating__avg']
        avg_rating = round(avg_rating, 1)
    
    has_purchased = False
    if request.user.role == 'student' and resource.is_premium:
        has_purchased = Payment.objects.filter(
            student=request.user,
            resource=resource,
            status='completed'
        ).exists()
    
    context = {
        'resource': resource,
        'feedbacks': feedbacks,
        'has_purchased': has_purchased,
        'avg_rating': avg_rating,
    }
    return render(request, 'myapp/resource_detail.html', context)

@login_required
@teacher_required
def upload_resource(request):
    """Handle resource uploads by teachers"""
    if request.method == 'POST':
        form = ResourceUploadForm(request.POST, request.FILES)
        if form.is_valid():
            resource = form.save(commit=False)
            resource.uploaded_by = request.user
            
            # Set file info
            file = request.FILES.get('file')
            if file:
                resource.file_size = file.size
                resource.file_type = os.path.splitext(file.name)[1].lower()
            
            resource.save()
            
            messages.success(request, 'Resource uploaded successfully!')
            return redirect('my_resources')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResourceUploadForm()
    
    categories = Category.objects.all()
    
    context = {
        'form': form,
        'categories': categories,
    }
    return render(request, 'myapp/upload_resource.html', context)

@login_required
@teacher_required
def my_resources(request):
    """View all resources uploaded by the teacher"""
    all_resources = Resource.objects.filter(uploaded_by=request.user)
    
    filter_type = request.GET.get('filter', 'all')
    
    if filter_type == 'premium':
        resources = all_resources.filter(is_premium=True)
    elif filter_type == 'free':
        resources = all_resources.filter(is_premium=False)
    else:
        resources = all_resources
    
    resources = resources.order_by('-uploaded_date')
    
    resource_count = all_resources.count()
    premium_count = all_resources.filter(is_premium=True).count()
    free_count = all_resources.filter(is_premium=False).count()
    
    total_downloads = 0
    for resource in all_resources:
        download_count = getattr(resource, 'download_count', 0)
        if download_count:
            total_downloads += download_count
    
    context = {
        'resources': resources,
        'resource_count': resource_count,
        'premium_count': premium_count,
        'free_count': free_count,
        'total_downloads': total_downloads,
    }
    
    return render(request, 'myapp/my_resources_teacher.html', context)

# ========== PAYMENT VIEWS ==========

@login_required
@student_required
def payment_options(request, resource_id):
    """Show payment options for a resource"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    # Check if already purchased
    if Payment.objects.filter(
        student=request.user,
        resource=resource,
        status='completed'
    ).exists():
        messages.info(request, 'You already own this resource!')
        return redirect('resource_detail', resource_id=resource_id)
    
    context = {
        'resource': resource,
    }
    return render(request, 'myapp/payment_options.html', context)

@login_required
@student_required
def demo_payment(request, resource_id):
    """Demo payment for testing"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if not resource.is_premium:
        messages.info(request, 'This resource is already free!')
        return redirect('resource_detail', resource_id=resource_id)
    
    existing_payment = Payment.objects.filter(
        student=request.user,
        resource=resource,
        status='completed'
    ).exists()
    
    if existing_payment:
        messages.info(request, 'You already purchased this resource!')
        return redirect('resource_detail', resource_id=resource_id)
    
    payment = Payment.objects.create(
        student=request.user,
        resource=resource,
        amount=resource.price,
        status='completed',
        payment_method='demo',
        transaction_id=f"DEMO_{int(time.time())}"
    )
    
    Notification.objects.create(
        sender=request.user,
        receiver=resource.uploaded_by,
        message=f"Student {request.user.username} DEMO purchased your resource: {resource.title} (${resource.price})"
    )
    
    messages.success(request, f'✅ Demo purchase successful! "{resource.title}" is now unlocked!')
    return redirect('resource_detail', resource_id=resource_id)

# ========== DOWNLOAD VIEW ==========

@login_required
def download_resource(request, resource_id):
    """Download a resource file"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if resource.is_premium and request.user.role == 'student':
        has_purchased = Payment.objects.filter(
            student=request.user,
            resource=resource,
            status='completed'
        ).exists()
        
        if not has_purchased:
            messages.error(request, 'You need to purchase this premium resource first.')
            return redirect('resource_detail', resource_id=resource_id)
    
    if not resource.file or not os.path.exists(resource.file.path):
        messages.error(request, 'File not found.')
        return redirect('resource_detail', resource_id=resource_id)
    
    # Update views and download count
    resource.views += 1
    resource.download_count = getattr(resource, 'download_count', 0) + 1
    resource.save()
    
    # Create download notification for teacher
    if request.user.role == 'student' and resource.uploaded_by and resource.uploaded_by != request.user:
        try:
            Notification.objects.create(
                sender=request.user,
                receiver=resource.uploaded_by,
                notification_type='download',
                message=f"Student {request.user.username} downloaded your resource: {resource.title}",
                resource=resource
            )
        except Exception as e:
            print(f"Error creating download notification: {e}")
    
    # Send file response
    response = FileResponse(resource.file.open('rb'))
    filename = os.path.basename(resource.file.name)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

# ========== FEEDBACK VIEW ==========

@login_required
def submit_feedback(request, resource_id):
    """Submit feedback for a resource"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if request.method == 'POST':
        message = request.POST.get('message', '').strip()
        rating = request.POST.get('rating', 5)
        
        if not message:
            messages.error(request, 'Please enter feedback message.')
            return redirect('resource_detail', resource_id=resource_id)
        
        if not rating.isdigit() or int(rating) < 1 or int(rating) > 5:
            rating = 5
        else:
            rating = int(rating)
        
        # Create feedback
        feedback = Feedback.objects.create(
            user=request.user,
            resource=resource,
            message=message,
            rating=rating
        )
        
        # Create notification for teacher
        if resource.uploaded_by and resource.uploaded_by != request.user:
            stars = '★' * rating + '☆' * (5 - rating)
            
            notification_message = f"{request.user.username} gave {stars} rating and feedback on your resource: {resource.title}"
            
            Notification.objects.create(
                receiver=resource.uploaded_by,
                sender=request.user,
                notification_type='feedback',
                message=notification_message,
                resource=resource
            )
            
            messages.success(request, 'Thank you for your feedback! The teacher has been notified.')
        else:
            messages.success(request, 'Thank you for your feedback!')
        
        return redirect('resource_detail', resource_id=resource_id)
    
    return redirect('resource_detail', resource_id=resource_id)

# ========== NOTIFICATION VIEWS ==========

@login_required
def mark_notification_read(request, notification_id):
    """Mark a notification as read"""
    notification = get_object_or_404(Notification, id=notification_id, receiver=request.user)
    notification.is_read = True
    notification.save()
    
    return redirect(request.META.get('HTTP_REFERER', 'teacher_dashboard'))

# ========== PROFILE VIEWS ==========

@login_required
def view_profile(request, user_id=None):
    """View user profile"""
    if user_id is None:
        user = request.user
    else:
        if request.user.role == 'admin' or request.user.id == user_id:
            user = get_object_or_404(User, id=user_id)
        else:
            messages.error(request, 'You do not have permission to view this profile.')
            return redirect('dashboard')
    
    uploaded_resources = []
    if user.role == 'teacher':
        uploaded_resources = Resource.objects.filter(uploaded_by=user).order_by('-uploaded_date')[:10]
    
    purchases = []
    if user.role == 'student':
        purchases = Payment.objects.filter(student=user, status='completed').select_related('resource')[:10]
    
    context = {
        'profile_user': user,
        'uploaded_resources': uploaded_resources,
        'purchases': purchases,
    }
    
    return render(request, 'myapp/profile.html', context)

def edit_profile(request):
    if request.method == 'POST':
        user = request.user
        
        # Update basic fields
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.email = request.POST.get('email', '').strip()
        user.phone = request.POST.get('phone', '').strip()
        
        # Handle program selection
        program = request.POST.get('program', '').strip()
        if program in dict(User.PROGRAM_CHOICES):
            user.program = program
        
        # Handle semester - convert to int or set to None
        semester = request.POST.get('semester', '').strip()
        if semester:
            try:
                user.semester = int(semester)
            except ValueError:
                user.semester = None
        else:
            user.semester = None
        
        # Handle other optional fields
        user.address = request.POST.get('address', '').strip()
        user.city = request.POST.get('city', '').strip()
        user.state = request.POST.get('state', '').strip()
        user.zip_code = request.POST.get('zip_code', '').strip()
        
        # Save the user
        user.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('edit_profile')
    
    return render(request, 'edit_profile.html')

# ========== ADMIN MANAGEMENT VIEWS ==========

@login_required
@admin_required
def manage_users(request):
    """Manage users view"""
    if request.GET.get('export') == 'csv':
        return export_users_csv(request)
    
    role_filter = request.GET.get('role', '')
    search_query = request.GET.get('search', '')
    
    users = User.objects.all().order_by('-date_joined')
    
    if role_filter:
        users = users.filter(role=role_filter)
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    total_users = users.count()
    active_users = users.filter(is_active=True).count()
    inactive_users = users.filter(is_active=False).count()
    
    week_ago = datetime.now() - timedelta(days=7)
    new_users_week = users.filter(date_joined__gte=week_ago).count()
    
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'users': page_obj,
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': inactive_users,
        'new_users_week': new_users_week,
    }
    
    return render(request, 'myapp/manage_users.html', context)

def export_users_csv(request):
    """Export users data to CSV"""
    role_filter = request.GET.get('role', '')
    search_query = request.GET.get('search', '')
    
    users = User.objects.all().order_by('-date_joined')
    
    if role_filter:
        users = users.filter(role=role_filter)
    
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="users_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    
    writer.writerow([
        'ID', 'Username', 'Full Name', 'Email', 'Role', 
        'Status', 'Date Joined', 'Last Login', 'Phone', 'Student ID',
        'Program', 'Semester', 'Shift'
    ])
    
    for user in users:
        writer.writerow([
            user.id,
            user.username,
            user.get_full_name() or '-',
            user.email,
            user.role or 'student',
            'Active' if user.is_active else 'Inactive',
            user.date_joined.strftime('%Y-%m-%d %H:%M:%S'),
            user.last_login.strftime('%Y-%m-%d %H:%M:%S') if user.last_login else 'Never',
            getattr(user, 'phone', '') or '',
            getattr(user, 'student_id', '') or '',
            getattr(user, 'program', '') or '',
            getattr(user, 'semester', '') or '',
            getattr(user, 'shift', '') or ''
        ])
    
    return response

@login_required
@admin_required
def manage_payments(request):
    """Admin view to manage payments"""
    if request.GET.get('export') == 'csv':
        return export_payments_csv(request)
    
    status_filter = request.GET.get('status', '')
    method_filter = request.GET.get('method', '')
    search_query = request.GET.get('search', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    payments = Payment.objects.all().select_related('student', 'resource').order_by('-payment_date')
    
    if status_filter:
        payments = payments.filter(status=status_filter)
    
    if method_filter:
        payments = payments.filter(payment_method=method_filter)
    
    if search_query:
        payments = payments.filter(
            Q(student__username__icontains=search_query) |
            Q(resource__title__icontains=search_query) |
            Q(transaction_id__icontains=search_query) |
            Q(student__email__icontains=search_query)
        )
    
    if start_date:
        payments = payments.filter(payment_date__date__gte=start_date)
    
    if end_date:
        payments = payments.filter(payment_date__date__lte=end_date)
    
    total_count = payments.count()
    
    status_stats = payments.values('status').annotate(
        count=Count('id'),
        total_amount=Sum('amount')
    )
    
    completed_count = 0
    pending_count = 0
    failed_count = 0
    refunded_count = 0
    completed_amount = 0
    pending_amount = 0
    failed_amount = 0
    
    for stat in status_stats:
        if stat['status'] == 'completed':
            completed_count = stat['count']
            completed_amount = stat['total_amount'] or 0
        elif stat['status'] == 'pending':
            pending_count = stat['count']
            pending_amount = stat['total_amount'] or 0
        elif stat['status'] == 'failed':
            failed_count = stat['count']
            failed_amount = stat['total_amount'] or 0
        elif stat['status'] == 'refunded':
            refunded_count = stat['count']
    
    this_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month_revenue = Payment.objects.filter(
        status='completed',
        payment_date__gte=this_month_start
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_revenue = Payment.objects.filter(
        status='completed',
        payment_date__gte=today_start
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    paginator = Paginator(payments, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'payments': page_obj,
        'total_count': total_count,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'failed_count': failed_count,
        'refunded_count': refunded_count,
        'completed_amount': completed_amount,
        'pending_amount': pending_amount,
        'failed_amount': failed_amount,
        'this_month_revenue': this_month_revenue,
        'today_revenue': today_revenue,
        'status_filter': status_filter,
        'method_filter': method_filter,
        'search_query': search_query,
        'start_date': start_date,
        'end_date': end_date,
    }
    
    return render(request, 'myapp/manage_payments.html', context)

def export_payments_csv(request):
    """Export payments data to CSV"""
    status_filter = request.GET.get('status', '')
    method_filter = request.GET.get('method', '')
    search_query = request.GET.get('search', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    payments = Payment.objects.all().select_related('student', 'resource', 'resource__uploaded_by').order_by('-payment_date')
    
    if status_filter:
        payments = payments.filter(status=status_filter)
    
    if method_filter:
        payments = payments.filter(payment_method=method_filter)
    
    if search_query:
        payments = payments.filter(
            Q(student__username__icontains=search_query) |
            Q(resource__title__icontains=search_query) |
            Q(transaction_id__icontains=search_query) |
            Q(student__email__icontains=search_query)
        )
    
    if start_date:
        payments = payments.filter(payment_date__date__gte=start_date)
    
    if end_date:
        payments = payments.filter(payment_date__date__lte=end_date)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="payments_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    
    writer.writerow([
        'Payment ID', 
        'Transaction ID', 
        'Student Username', 
        'Student Email',
        'Student ID',
        'Resource ID',
        'Resource Title', 
        'Resource Price ($)', 
        'Amount Paid ($)', 
        'Status', 
        'Payment Method',
        'Payment Date', 
        'eSewa Reference', 
        'Teacher Username',
        'Teacher Email'
    ])
    
    for payment in payments:
        writer.writerow([
            payment.id,
            payment.transaction_id or 'N/A',
            payment.student.username,
            payment.student.email,
            getattr(payment.student, 'student_id', '') or 'N/A',
            payment.resource.id,
            payment.resource.title,
            payment.resource.price,
            payment.amount,
            payment.status,
            payment.payment_method,
            payment.payment_date.strftime('%Y-%m-%d %H:%M:%S'),
            payment.esewa_ref_id or 'N/A',
            payment.resource.uploaded_by.username,
            payment.resource.uploaded_by.email
        ])
    
    return response

@login_required
@admin_required
def toggle_user_status(request, user_id):
    """Activate/Deactivate user account"""
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        if user.is_active:
            user.is_active = False
            action = "deactivated"
        else:
            user.is_active = True
            action = "activated"
        
        user.save()
        messages.success(request, f'User {user.username} has been {action}.')
    
    return redirect('manage_users')

# ========== OTHER VIEWS ==========

@login_required
@admin_required
def add_category(request):
    """Add new category (admin only)"""
    categories = Category.objects.all()
    
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save()
            messages.success(request, f'Category "{category.name}" created successfully.')
            return redirect('admin_dashboard')
    else:
        form = CategoryForm()
    
    return render(request, 'myapp/add_category.html', {
        'form': form,
        'categories': categories,
    })

@login_required
@admin_required
def create_teacher_account(request):
    """Create teacher account (admin only)"""
    if request.method == 'POST':
        form = TeacherCreationForm(request.POST)
        if form.is_valid():
            teacher = form.save()
            
            Notification.objects.create(
                sender=request.user,
                receiver=request.user,
                message=f"Teacher account created for {teacher.username}"
            )
            
            messages.success(request, f'Teacher account created for {teacher.username}')
            return redirect('admin_dashboard')
        else:
            for error in form.errors.values():
                messages.error(request, error)
    else:
        form = TeacherCreationForm()
    
    context = {'form': form}
    return render(request, 'myapp/create_teacher.html', context)

# ========== MISSING FUNCTIONS THAT WERE IN YOUR ORIGINAL ==========

@login_required
@student_required
def student_purchased_resources(request):
    """View for students to see their purchased resources"""
    if request.user.role != 'student':
        return redirect('dashboard')
    
    purchased_payments = Payment.objects.filter(
        student=request.user,
        status='completed'
    ).select_related('resource')
    
    purchased_resource_ids = purchased_payments.values_list('resource_id', flat=True)
    
    purchased_resources = Resource.objects.filter(
        id__in=purchased_resource_ids
    ).order_by('-uploaded_date')
    
    free_resources = Resource.objects.filter(
        is_premium=False
    ).order_by('-uploaded_date')
    
    context = {
        'purchased_resources': purchased_resources,
        'free_resources': free_resources,
        'total_purchased': purchased_resources.count(),
        'total_free': free_resources.count(),
    }
    
    return render(request, 'myapp/student_purchased_resources.html', context)

@login_required
def student_profile(request):
    """Simple student profile page"""
    if request.user.role != 'student':
        return redirect('dashboard')
    
    completed_purchases_count = Payment.objects.filter(
        student=request.user, 
        status='completed'
    ).count()
    
    feedback_count = Feedback.objects.filter(
        user=request.user
    ).count()
    
    context = {
        'profile_user': request.user,
        'completed_purchases_count': completed_purchases_count,
        'feedback_count': feedback_count,
    }
    
    return render(request, 'myapp/profile.html', context)

@login_required
def update_student_profile(request):
    """Update student profile information"""
    if request.method == 'POST':
        user = request.user
        full_name = request.POST.get('full_name', '')
        if full_name:
            name_parts = full_name.split()
            user.first_name = name_parts[0] if name_parts else ''
            user.last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
        user.phone = request.POST.get('phone', '')
        user.program = request.POST.get('program', '')
        user.semester = request.POST.get('semester', '')
        user.save()
        messages.success(request, 'Profile updated successfully!')
    return redirect('student_profile')

@login_required
@admin_required
def edit_user_admin(request, user_id):
    """Admin edit user details"""
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        try:
            user.username = request.POST.get('username', user.username)
            user.email = request.POST.get('email', user.email)
            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            
            new_role = request.POST.get('role', user.role)
            user.role = new_role
            
            is_active = request.POST.get('is_active') == 'true'
            user.is_active = is_active
            
            user.phone = request.POST.get('phone', '')
            user.address = request.POST.get('address', '')
            
            if new_role == 'student':
                user.student_id = request.POST.get('student_id', '')
                user.program = request.POST.get('program', '')
                
                semester = request.POST.get('semester', '')
                user.semester = int(semester) if semester.isdigit() else None
                
                user.shift = request.POST.get('shift', '')
            else:
                user.student_id = ''
                user.program = ''
                user.semester = None
                user.shift = ''
            
            user.save()
            messages.success(request, f'User {user.username} updated successfully!')
            
            Notification.objects.create(
                sender=request.user,
                receiver=user,
                message=f"Admin {request.user.username} updated your account details"
            )
            
            return redirect('manage_users')
            
        except Exception as e:
            messages.error(request, f'Error updating user: {str(e)}')
    
    context = {'user': user}
    return render(request, 'myapp/edit_user_admin.html', context)

@login_required
def initiate_payment(request, resource_id):
    """Initiate payment for a resource"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    existing_payment = Payment.objects.filter(
        student=request.user,
        resource=resource,
        status='completed'
    ).first()
    
    if existing_payment:
        messages.info(request, 'You already purchased this resource.')
        return redirect('resource_detail', resource_id=resource_id)
    
    payment_method = request.GET.get('method', 'demo')
    
    payment = Payment.objects.create(
        student=request.user,
        resource=resource,
        amount=resource.price,
        status='pending',
        payment_method=payment_method
    )
    
    context = {
        'resource': resource,
        'payment': payment,
    }
    return render(request, 'myapp/payment_processing.html', context)

@login_required
def payment_success(request, payment_id):
    """Handle successful payment"""
    payment = get_object_or_404(Payment, id=payment_id, student=request.user)
    
    if payment.status != 'completed':
        payment.status = 'completed'
        payment.save()
        
        Notification.objects.create(
            sender=request.user,
            receiver=payment.resource.uploaded_by,
            message=f"Student {request.user.username} purchased your resource: {payment.resource.title}"
        )
        
        messages.success(request, 'Payment successful! You can now download the resource.')
    
    context = {
        'payment': payment,
    }
    return render(request, 'myapp/payment_success.html', context)

@login_required
def payment_failed(request, payment_id):
    """Handle failed payment"""
    payment = get_object_or_404(Payment, id=payment_id, student=request.user)
    
    if request.method == 'POST':
        payment.status = 'failed'
        payment.save()
        
        messages.error(request, 'Payment failed. Please try again.')
        return redirect('payment_options', resource_id=payment.resource.id)
    
    context = {
        'payment': payment,
        'resource': payment.resource,
    }
    return render(request, 'myapp/payment_failed.html', context)

@login_required
@admin_required
def payment_details_api(request, payment_id):
    """API endpoint for payment details (for modal in manage_payments)"""
    try:
        payment = Payment.objects.select_related('student', 'resource').get(id=payment_id)
        
        if not (request.user.role == 'admin' or request.user.is_staff):
            return JsonResponse({
                'success': False, 
                'error': 'Permission denied'
            }, status=403)
        
        data = {
            'success': True,
            'payment': {
                'id': payment.id,
                'transaction_id': payment.transaction_id,
                'amount': float(payment.amount),
                'status': payment.status,
                'payment_method': payment.payment_method,
                'payment_date': payment.payment_date.isoformat(),
                'esewa_ref_id': payment.esewa_ref_id,
                'student': {
                    'username': payment.student.username,
                    'email': payment.student.email,
                    'student_id': payment.student.student_id,
                },
                'resource': {
                    'title': payment.resource.title,
                    'description': payment.resource.description,
                    'is_premium': payment.resource.is_premium,
                    'uploaded_by': {
                        'username': payment.resource.uploaded_by.username,
                    }
                }
            }
        }
        return JsonResponse(data)
        
    except Payment.DoesNotExist:
        return JsonResponse({
            'success': False, 
            'error': 'Payment not found'
        }, status=404)
        
    except Exception as e:
        return JsonResponse({
            'success': False, 
            'error': str(e)
        }, status=500)

@login_required
@teacher_required  
def delete_resource(request, resource_id):
    """Delete a resource (teacher only)"""
    resource = get_object_or_404(Resource, id=resource_id, uploaded_by=request.user)
    
    if request.method == 'POST':
        if resource.file and os.path.exists(resource.file.path):
            os.remove(resource.file.path)
        
        resource_title = resource.title
        resource.delete()
        
        messages.success(request, f'Resource "{resource_title}" deleted successfully!')
        return redirect('teacher_dashboard')
    
    return render(request, 'myapp/confirm_delete.html', {'resource': resource})

@login_required
@admin_required
def manage_resources(request):
    """Admin view to manage all resources"""
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    
    resources = Resource.objects.all().order_by('-uploaded_date')
    
    if category_filter:
        resources = resources.filter(category__id=category_filter)
    
    if status_filter:
        if status_filter == 'free':
            resources = resources.filter(price=0)
        elif status_filter == 'premium':
            resources = resources.filter(price__gt=0)
    
    if search_query:
        resources = resources.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(uploaded_by__username__icontains=search_query)
        )
    
    categories = Category.objects.all()
    
    paginator = Paginator(resources, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'resources': page_obj,
        'categories': categories,
        'total_resources': resources.count(),
        'free_resources': resources.filter(price=0).count(),
        'premium_resources': resources.filter(price__gt=0).count(),
    }
    
    return render(request, 'myapp/manage_resources.html', context)

@login_required
@teacher_required
def edit_resource(request, resource_id):
    """Edit a resource (teacher only)"""
    resource = get_object_or_404(Resource, id=resource_id, uploaded_by=request.user)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        category_id = request.POST.get('category')
        is_premium = request.POST.get('is_premium') == 'true'
        price = request.POST.get('price', 0)
        
        resource.title = title
        resource.description = description
        resource.is_premium = is_premium
        
        if is_premium:
            resource.price = price
        else:
            resource.price = 0
        
        if category_id:
            try:
                category = Category.objects.get(id=category_id)
                resource.category = category
            except Category.DoesNotExist:
                resource.category = None
        else:
            resource.category = None
        
        if 'file' in request.FILES:
            if resource.file and os.path.exists(resource.file.path):
                os.remove(resource.file.path)
            resource.file = request.FILES['file']
        
        resource.save()
        
        messages.success(request, f'Resource "{resource.title}" updated successfully!')
        return redirect('resource_detail', resource_id=resource.id)
    
    categories = Category.objects.all()
    context = {
        'resource': resource,
        'categories': categories,
    }
    return render(request, 'myapp/edit_resource.html', context)

@login_required
@admin_required
def update_payment_status(request, payment_id):
    """Admin can update payment status"""
    payment = get_object_or_404(Payment, id=payment_id)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        
        if new_status in ['completed', 'pending', 'failed', 'refunded']:
            old_status = payment.status
            payment.status = new_status
            payment.save()
            
            Notification.objects.create(
                sender=request.user,
                receiver=payment.student,
                message=f"Admin updated your payment status for '{payment.resource.title}' from {old_status} to {new_status}"
            )
            
            messages.success(request, f'Payment status updated to {new_status}.')
    
    return redirect('manage_payments')

@login_required
def resource_stats(request, resource_id):
    """View statistics for a specific resource"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if not (request.user == resource.uploaded_by or request.user.is_staff):
        messages.error(request, "You don't have permission to view these stats.")
        return redirect('resource_detail', resource_id=resource_id)
    
    feedbacks = Feedback.objects.filter(resource=resource)
    average_rating = feedbacks.aggregate(Avg('rating'))['rating__avg'] or 0
    
    context = {
        'resource': resource,
        'feedbacks': feedbacks,
        'average_rating': round(average_rating, 1),
        'download_count': resource.download_count or 0,
        'total_views': resource.views or 0,
    }
    return render(request, 'myapp/resource_stats.html', context)

@login_required
def teacher_notifications(request):
    """View all notifications for teacher"""
    notifications = Notification.objects.filter(receiver=request.user).order_by('-created_at')
    
    if request.method == 'GET':
        unread_notifications = notifications.filter(is_read=False)
        if unread_notifications.exists():
            unread_notifications.update(is_read=True)
    
    context = {
        'notifications': notifications,
        'unread_count': 0,
    }
    return render(request, 'myapp/teacher_notifications.html', context)

@login_required
def teacher_settings(request):
    """Teacher settings page"""
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        
        user = request.user
        
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        if email:
            user.email = email
        
        user.save()
        
        messages.success(request, 'Profile updated successfully!')
        return redirect('teacher_settings')
    
    context = {
        'user': request.user,
    }
    return render(request, 'myapp/teacher_settings.html', context)

@login_required
@admin_required
def delete_resource_admin(request, resource_id):
    """Admin can delete any resource"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if request.method == 'POST':
        if resource.file and os.path.exists(resource.file.path):
            os.remove(resource.file.path)
        
        resource_title = resource.title
        resource.delete()
        
        messages.success(request, f'Resource "{resource_title}" deleted successfully!')
        return redirect('manage_resources')
    
    return render(request, 'myapp/admin_confirm_delete.html', {'resource': resource})


@login_required
@student_required
def purchase_resource(request, resource_id):
    """Handle resource purchase - redirects to payment options"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    # Check if already purchased
    if Payment.objects.filter(
        student=request.user,
        resource=resource,
        status='completed'
    ).exists():
        messages.info(request, 'You already own this resource!')
        return redirect('resource_detail', resource_id=resource_id)
    
    # Redirect to payment options
    return redirect('payment_options', resource_id=resource_id)

# ========== MISSING VIEWS NEEDED FOR YOUR URLS.PY ==========

@login_required
@student_required
def purchase_resource(request, resource_id):
    """Handle resource purchase - redirects to payment options"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    # Check if already purchased
    if Payment.objects.filter(
        student=request.user,
        resource=resource,
        status='completed'
    ).exists():
        messages.info(request, 'You already own this resource!')
        return redirect('resource_detail', resource_id=resource_id)
    
    # Redirect to payment options
    return redirect('payment_options', resource_id=resource_id)

@login_required
@teacher_required
def edit_resource(request, resource_id):
    """Edit a resource (teacher only)"""
    resource = get_object_or_404(Resource, id=resource_id, uploaded_by=request.user)
    
    if request.method == 'POST':
        # Get form data
        title = request.POST.get('title')
        description = request.POST.get('description')
        category_id = request.POST.get('category')
        is_premium = request.POST.get('is_premium') == 'true'
        price = request.POST.get('price', 0)
        
        # Update resource
        resource.title = title
        resource.description = description
        resource.is_premium = is_premium
        
        if is_premium:
            resource.price = price
        else:
            resource.price = 0
        
        # Update category if selected
        if category_id:
            try:
                category = Category.objects.get(id=category_id)
                resource.category = category
            except Category.DoesNotExist:
                resource.category = None
        else:
            resource.category = None
        
        # Handle file upload if new file provided
        if 'file' in request.FILES:
            # Delete old file if exists
            if resource.file and os.path.exists(resource.file.path):
                os.remove(resource.file.path)
            resource.file = request.FILES['file']
        
        resource.save()
        
        messages.success(request, f'Resource "{resource.title}" updated successfully!')
        return redirect('resource_detail', resource_id=resource.id)
    
    # GET request - show edit form
    categories = Category.objects.all()
    context = {
        'resource': resource,
        'categories': categories,
    }
    return render(request, 'myapp/edit_resource.html', context)

@login_required  
def delete_resource(request, resource_id):
    """Delete a resource (teacher only)"""
    resource = get_object_or_404(Resource, id=resource_id, uploaded_by=request.user)
    
    if request.method == 'POST':
        # Delete file from filesystem
        if resource.file and os.path.exists(resource.file.path):
            os.remove(resource.file.path)
        
        resource_title = resource.title
        resource.delete()
        
        messages.success(request, f'Resource "{resource_title}" deleted successfully!')
        return redirect('teacher_dashboard')
    
    # If GET request, show confirmation page
    return render(request, 'myapp/confirm_delete.html', {'resource': resource})

@login_required
@admin_required
def edit_user_admin(request, user_id):
    """Admin edit user details"""
    user = get_object_or_404(User, id=user_id)
    
    if request.method == 'POST':
        try:
            # Update basic user fields
            user.username = request.POST.get('username', user.username)
            user.email = request.POST.get('email', user.email)
            user.first_name = request.POST.get('first_name', '')
            user.last_name = request.POST.get('last_name', '')
            
            # Update role
            new_role = request.POST.get('role', user.role)
            user.role = new_role
            
            # Update active status
            is_active = request.POST.get('is_active') == 'true'
            user.is_active = is_active
            
            # Update contact info
            user.phone = request.POST.get('phone', '')
            user.address = request.POST.get('address', '')
            
            # Update student-specific fields if role is student
            if new_role == 'student':
                user.student_id = request.POST.get('student_id', '')
                user.program = request.POST.get('program', '')
                
                semester = request.POST.get('semester', '')
                user.semester = int(semester) if semester.isdigit() else None
                
                user.shift = request.POST.get('shift', '')
            else:
                # Clear student fields if changing role from student
                user.student_id = ''
                user.program = ''
                user.semester = None
                user.shift = ''
            
            user.save()
            messages.success(request, f'User {user.username} updated successfully!')
            
            # Send notification to user
            Notification.objects.create(
                sender=request.user,
                receiver=user,
                message=f"Admin {request.user.username} updated your account details"
            )
            
            return redirect('manage_users')
            
        except Exception as e:
            messages.error(request, f'Error updating user: {str(e)}')
    
    context = {'user': user}
    return render(request, 'myapp/edit_user_admin.html', context)

@login_required
@admin_required
def manage_resources(request):
    """Admin view to manage all resources"""
    # Get filter parameters
    category_filter = request.GET.get('category', '')
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')
    
    # Start with all resources
    resources = Resource.objects.all().order_by('-uploaded_date')
    
    # Apply filters
    if category_filter:
        resources = resources.filter(category__id=category_filter)
    
    if status_filter:
        if status_filter == 'free':
            resources = resources.filter(price=0)
        elif status_filter == 'premium':
            resources = resources.filter(price__gt=0)
    
    if search_query:
        resources = resources.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(uploaded_by__username__icontains=search_query)
        )
    
    # Get all categories for filter dropdown
    categories = Category.objects.all()
    
    # Pagination
    paginator = Paginator(resources, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'resources': page_obj,
        'categories': categories,
        'total_resources': resources.count(),
        'free_resources': resources.filter(price=0).count(),
        'premium_resources': resources.filter(price__gt=0).count(),
    }
    
    return render(request, 'myapp/manage_resources.html', context)

@login_required
@admin_required
def delete_resource_admin(request, resource_id):
    """Admin can delete any resource"""
    resource = get_object_or_404(Resource, id=resource_id)
    
    if request.method == 'POST':
        if resource.file and os.path.exists(resource.file.path):
            os.remove(resource.file.path)
        
        resource_title = resource.title
        resource.delete()
        
        messages.success(request, f'Resource "{resource_title}" deleted successfully!')
        return redirect('manage_resources')
    
    return render(request, 'myapp/admin_confirm_delete.html', {'resource': resource})

@login_required
@admin_required
def update_payment_status(request, payment_id):
    """Admin can update payment status"""
    payment = get_object_or_404(Payment, id=payment_id)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        
        if new_status in ['completed', 'pending', 'failed', 'refunded']:
            old_status = payment.status
            payment.status = new_status
            payment.save()
            
            Notification.objects.create(
                sender=request.user,
                receiver=payment.student,
                message=f"Admin updated your payment status for '{payment.resource.title}' from {old_status} to {new_status}"
            )
            
            messages.success(request, f'Payment status updated to {new_status}.')
    
    return redirect('manage_payments')



def test_view(request):
    """Simple test view"""
    return render(request, 'myapp/test.html')