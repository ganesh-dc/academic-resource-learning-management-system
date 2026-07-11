from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid
import time
import re

# Custom User model
class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    ]
    
    PROGRAM_CHOICES = [
        ('BIM', 'BIM (Bachelor of Information Management)'),
        ('BCA', 'BCA (Bachelor of Computer Application)'),
        ('BBA', 'BBA (Bachelor of Business Administration)'),
        ('BBM', 'BBM (Bachelor of Business Management)'),
        ('BBS', 'BBS (Bachelor of Business Studies)'),
        ('B.Sc.', 'B.Sc. (Bachelor of Science)'),
        ('BA', 'BA (Bachelor of Arts)'),
        ('other', 'Other'),
    ]
    
    SHIFT_CHOICES = [
        ('morning', 'Morning Shift'),
        ('day', 'Day Shift'),
        ('evening', 'Evening Shift'),
    ]
    
    SECTION_CHOICES = [
        ('A', 'Section A'),
        ('B', 'Section B'),
        ('C', 'Section C'),
        ('D', 'Section D'),
        ('E', 'Section E'),
        ('', 'Not Specified'),
    ]
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    phone = models.CharField(max_length=15, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Student-specific fields (updated for registration)
    student_id = models.CharField(max_length=20, blank=True, unique=True, null=True)
    full_name = models.CharField(max_length=100, blank=True)
    program = models.CharField(max_length=50, choices=PROGRAM_CHOICES, blank=True)
    semester = models.IntegerField(null=True, blank=True)
    shift = models.CharField(max_length=20, choices=SHIFT_CHOICES, blank=True)  # Changed from section to shift
    address = models.TextField(blank=True)
    
    # Email verification fields
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.CharField(max_length=100, blank=True)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Phone verification fields
    is_phone_verified = models.BooleanField(default=False)
    phone_verification_otp = models.CharField(max_length=6, blank=True)
    phone_otp_sent_at = models.DateTimeField(null=True, blank=True)
    
    # OTP fields for registration
    registration_otp = models.CharField(max_length=6, blank=True)
    registration_otp_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Account status
    verification_status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending Verification'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ])
    
    # Additional fields for tracking
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    registration_ip = models.GenericIPAddressField(blank=True, null=True)
    registration_completed = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-date_joined']
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        if self.role == 'student' and self.full_name:
            return f"{self.full_name} ({self.username})"
        return f"{self.username} ({self.role})"
    
    def clean_phone(self):
        """Clean and validate phone number"""
        if self.phone:
            # Remove all non-digit characters
            phone_clean = re.sub(r'\D', '', str(self.phone))
            
            # Add country code for Nepal if missing
            if phone_clean and len(phone_clean) == 10:
                if phone_clean.startswith(('98', '97', '96')):  # Common Nepal mobile prefixes
                    phone_clean = '977' + phone_clean
            
            return phone_clean
        return self.phone
    
    def is_valid_phone(self):
        """Check if phone number is valid"""
        if not self.phone:
            return False
        
        phone_clean = self.clean_phone()
        # Nepal phone numbers: 977 (country) + 98/97 (mobile) + 8 digits
        return len(phone_clean) >= 10 and phone_clean.isdigit()
    
    def save(self, *args, **kwargs):
        """Override save to clean phone number before saving"""
        if self.phone:
            self.phone = self.clean_phone()
        
        # Set verification status
        if self.is_email_verified:
            self.verification_status = 'verified'
        
        # Auto-generate student ID if not provided for students
        if self.role == 'student' and not self.student_id and self.username:
            # Generate a temporary student ID
            self.student_id = f"TEMP_{self.username}_{int(time.time())}"
        
        super().save(*args, **kwargs)
    
    def get_student_display(self):
        """Format student information for display"""
        if self.role != 'student':
            return self.username
        
        info = []
        if self.full_name:
            info.append(self.full_name)
        if self.student_id and not self.student_id.startswith('TEMP_'):
            info.append(f"ID: {self.student_id}")
        if self.program:
            program_display = dict(self.PROGRAM_CHOICES).get(self.program, self.program)
            info.append(program_display)
        if self.semester:
            info.append(f"Sem {self.semester}")
        if self.shift:
            info.append(f"{self.shift.capitalize()} Shift")
        
        return " | ".join(info) if info else self.username
    
    def get_program_display(self):
        """Get human-readable program name"""
        if not self.program:
            return ""
        return dict(self.PROGRAM_CHOICES).get(self.program, self.program)
    
    def get_verification_badge(self):
        """Get HTML badge for verification status"""
        if self.verification_status == 'verified':
            return '<span class="badge bg-success">✓ Verified</span>'
        elif self.verification_status == 'rejected':
            return '<span class="badge bg-danger">✗ Rejected</span>'
        else:
            return '<span class="badge bg-warning">⏳ Pending</span>'
    
    def can_access_premium(self):
        """Check if user can access premium content"""
        if self.role in ['admin', 'teacher']:
            return True
        
        if self.role == 'student':
            return self.verification_status == 'verified' and self.is_email_verified
        
        return False
    
    def is_otp_valid(self):
        """Check if registration OTP is still valid (10 minutes)"""
        if not self.registration_otp or not self.registration_otp_sent_at:
            return False
        
        time_diff = (timezone.now() - self.registration_otp_sent_at).total_seconds()
        return time_diff <= 600  # 10 minutes
    
    def mark_as_registered(self, ip_address=None):
        """Mark user as registered successfully"""
        self.registration_completed = True
        if ip_address:
            self.registration_ip = ip_address
        self.save()
    
    def generate_email_token(self):
        """Generate email verification token"""
        token = str(uuid.uuid4())
        self.email_verification_token = token
        self.email_verification_sent_at = timezone.now()
        self.save()
        return token


class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)  # Changed to default
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.pk:  # Only set created_at on first save
            self.created_at = timezone.now()
        super().save(*args, **kwargs)


class Resource(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    file = models.FileField(upload_to='resources/%Y/%m/%d/')
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_resources')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_date = models.DateTimeField(auto_now_add=True)
    is_premium = models.BooleanField(default=False)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    views = models.IntegerField(default=0)
    download_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    file_size = models.BigIntegerField(default=0)  # Size in bytes
    file_type = models.CharField(max_length=50, blank=True)
    
    class Meta:
        ordering = ['-uploaded_date']
    
    def __str__(self):
        return self.title
    
    def increment_view(self):
        """Increment view count"""
        self.views += 1
        self.save(update_fields=['views'])
    
    def increment_download(self):
        """Increment download count"""
        self.download_count += 1
        self.save(update_fields=['download_count'])
    
    def get_file_size_display(self):
        """Convert file size to human readable format"""
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        elif self.file_size < 1024 * 1024 * 1024:
            return f"{self.file_size / (1024 * 1024):.1f} MB"
        else:
            return f"{self.file_size / (1024 * 1024 * 1024):.1f} GB"


class Feedback(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='feedbacks_given')
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, null=True, blank=True)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    rating = models.IntegerField(default=5, choices=[(i, i) for i in range(1, 6)])
    is_approved = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Feedback from {self.user}"
    
    def get_star_rating(self):
        """Get star rating HTML"""
        stars = '★' * self.rating + '☆' * (5 - self.rating)
        return f'<span class="text-warning">{stars}</span>'


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('feedback', 'New Feedback'),
        ('download', 'Resource Downloaded'),
        ('purchase', 'Resource Purchased'),
        ('system', 'System Notification'),
        ('verification', 'Verification'),
        ('registration', 'Registration'),
        ('otp', 'OTP Verification'),
    ]
    
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_notifications')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES, default='system')
    message = models.TextField()
    resource = models.ForeignKey('Resource', on_delete=models.SET_NULL, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.URLField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notification_type}: {self.message[:50]}"
    
    def mark_as_read(self):
        """Mark notification as read"""
        self.is_read = True
        self.save()
    
    def get_icon(self):
        icon_map = {
            'feedback': 'fa-comment',
            'download': 'fa-download',
            'purchase': 'fa-shopping-cart',
            'system': 'fa-bell',
            'verification': 'fa-check-circle',
            'registration': 'fa-user-plus',
            'otp': 'fa-key',
        }
        return icon_map.get(self.notification_type, 'fa-bell')
    
    def get_color(self):
        """Get appropriate color based on notification type"""
        color_map = {
            'feedback': 'text-warning',
            'download': 'text-success',
            'purchase': 'text-primary',
            'system': 'text-secondary',
            'verification': 'text-success',
            'registration': 'text-info',
            'otp': 'text-info',
        }
        return color_map.get(self.notification_type, 'text-secondary')


class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
        ('cancelled', 'Cancelled'),
    ]                   
    
    PAYMENT_METHOD_CHOICES = [
        ('esewa', 'eSewa'),
        
        
    ]
    
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='esewa')
    payment_date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.CharField(max_length=100, blank=True, unique=True)
    reference_id = models.CharField(max_length=100, blank=True)
    esewa_ref_id = models.CharField(max_length=100, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_reason = models.TextField(blank=True)
    transaction_uuid = models.CharField(max_length=100, unique=True, null=True, blank=True)
    khalti_pidx = models.CharField(max_length=100, blank=True, null=True)
    payment_provider_data = models.JSONField(blank=True, null=True)
    
    class Meta:
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"{self.student} - {self.resource} (${self.amount})"
    
    def generate_transaction_id(self):
        """Generate unique transaction ID"""
        timestamp = int(time.time())
        unique_id = str(uuid.uuid4())[:8]
        return f"ARLMS{timestamp}{unique_id}"
    
    def save(self, *args, **kwargs):
        # Generate transaction ID if not set
        if not self.transaction_id:
            self.transaction_id = self.generate_transaction_id()
        
        # Set completed_at if status changed to completed
        if self.pk:
            old_status = Payment.objects.get(pk=self.pk).status
            if old_status != 'completed' and self.status == 'completed':
                self.completed_at = timezone.now()
        
        super().save(*args, **kwargs)
    
    def mark_as_completed(self, reference_id=''):
        """Mark payment as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        if reference_id:
            self.reference_id = reference_id
        self.save()


class VerificationLog(models.Model):
    VERIFICATION_TYPES = [
        ('email', 'Email Verification'),
        ('phone', 'Phone Verification'),
        ('student_id', 'Student ID Verification'),
        ('registration', 'Registration OTP'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_logs')
    verification_type = models.CharField(max_length=20, choices=VERIFICATION_TYPES)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
    ])
    details = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user} - {self.verification_type} - {self.status}"
    
    @classmethod
    def log_verification(cls, user, verification_type, status, details='', ip_address=None):
        """Create a verification log entry"""
        return cls.objects.create(
            user=user,
            verification_type=verification_type,
            status=status,
            details=details,
            ip_address=ip_address
        )


# New model for OTP storage (temporary)
class OTPStorage(models.Model):
    """Temporary storage for OTP verification"""
    email = models.EmailField(unique=True)
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    verified = models.BooleanField(default=False)
    attempts = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'OTP Storage'
        verbose_name_plural = 'OTP Storage'
    
    def __str__(self):
        return f"{self.email} - {self.otp}"
    
    def is_valid(self):
        """Check if OTP is still valid (10 minutes)"""
        time_diff = (timezone.now() - self.created_at).total_seconds()
        return time_diff <= 600 and self.attempts < 5
    
    def increment_attempts(self):
        """Increment failed attempts"""
        self.attempts += 1
        self.save()
    
    def mark_as_verified(self):
        """Mark OTP as verified"""
        self.verified = True
        self.save()
    
    @classmethod
    def cleanup_expired(cls):
        """Clean up expired OTPs"""
        expired_time = timezone.now() - timezone.timedelta(minutes=10)
        cls.objects.filter(created_at__lt=expired_time).delete()


# New model for registration attempts
class RegistrationAttempt(models.Model):
    """Track registration attempts for security"""
    email = models.EmailField()
    ip_address = models.GenericIPAddressField()
    attempt_count = models.IntegerField(default=1)
    last_attempt = models.DateTimeField(auto_now=True)
    is_blocked = models.BooleanField(default=False)
    blocked_until = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['email', 'ip_address']
    
    def __str__(self):
        return f"{self.email} - {self.ip_address}"
    
    def should_block(self):
        """Check if this attempt should be blocked"""
        # Block if more than 5 attempts in last hour
        time_threshold = timezone.now() - timezone.timedelta(hours=1)
        if self.attempt_count >= 5 and self.last_attempt > time_threshold:
            self.is_blocked = True
            self.blocked_until = timezone.now() + timezone.timedelta(hours=1)
            self.save()
            return True
        return False
    
    def increment_attempt(self):
        """Increment attempt count"""
        self.attempt_count += 1
        self.last_attempt = timezone.now()
        self.save()
    
    def reset_attempts(self):
        """Reset attempt count"""
        self.attempt_count = 0
        self.is_blocked = False
        self.blocked_until = None
        self.save()