from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required


urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('send-otp/', views.send_otp, name='send_otp'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('check-otp-status/', views.check_otp_status, name='check_otp_status'),
    
    
    # Password Reset URLs
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('verify-reset-otp/', views.verify_reset_otp, name='verify_reset_otp'),
    path('reset-password/', views.reset_password_view, name='reset_password'),
    path('reset-password-success/', views.reset_password_success, name='reset_password_success'),
    path('dashboard/', views.dashboard, name='dashboard'),
 
    # Dashboards
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('teacher-dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('student-dashboard/', views.student_dashboard, name='student_dashboard'),
    
    # Profile URLs - FIXED: Keep 'profile' for my profile and 'view_profile' for viewing others
    path('profile/', views.view_profile, name='profile'),  # For viewing own profile
    path('profile/<int:user_id>/', views.view_profile, name='view_profile'),  # For viewing others' profiles
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    
    # Student features
    path('student-profile/', views.student_profile, name='student_profile'),
    path('student/update-profile/', views.update_student_profile, name='update_student_profile'),
    
    # Student URLs
    path('student/purchased-resources/', views.student_purchased_resources, name='student_purchased_resources'),
    path('resources/<int:resource_id>/', views.resource_detail, name='resource_detail'),
    
    # Other resource URLs
    path('resources/', views.resource_list, name='resource_list'),
    path('upload/', views.upload_resource, name='upload_resource'),
    path('my-resources/', views.my_resources, name='my_resources'),
    path('download/<int:resource_id>/', views.download_resource, name='download_resource'),
    path('resource/edit/<int:resource_id>/', views.edit_resource, name='edit_resource'),
    path('resource/delete/<int:resource_id>/', views.delete_resource, name='delete_resource'),

    
    # Payment
    path('purchase/<int:resource_id>/', views.purchase_resource, name='purchase_resource'),
    path('payment-options/<int:resource_id>/', views.payment_options, name='payment_options'),
    path('initiate-payment/<int:resource_id>/', views.initiate_payment, name='initiate_payment'),
    path('payment-success/<int:payment_id>/', views.payment_success, name='payment_success'),
    path('payment-failed/<int:payment_id>/', views.payment_failed, name='payment_failed'),
    path('api/payment-details/<int:payment_id>/', views.payment_details_api, name='payment_details_api'),
     # eSewa Payment URLs
    path('payment/esewa/<int:resource_id>/', views.initiate_esewa_payment, name='initiate_esewa_payment'),
    path('payment/esewa/success/', views.esewa_success, name='esewa_success'),
    path('payment/esewa/failure/', views.esewa_failure, name='esewa_failure'),
    
 
    
    
    # Feedback & Notifications
    path('feedback/<int:resource_id>/', views.submit_feedback, name='submit_feedback'),
    path('notification/read/<int:notification_id>/', views.mark_notification_read, name='mark_notification_read'),
    
    # Admin management URLs
    path('manage-users/', views.manage_users, name='manage_users'),
    path('edit-user-admin/<int:user_id>/', views.edit_user_admin, name='edit_user_admin'),
    path('manage-resources/', views.manage_resources, name='manage_resources'),
    path('manage-payments/', views.manage_payments, name='manage_payments'),
    path('toggle-user-status/<int:user_id>/', views.toggle_user_status, name='toggle_user_status'),
    path('delete-resource-admin/<int:resource_id>/', views.delete_resource_admin, name='delete_resource_admin'),
    path('update-payment-status/<int:payment_id>/', views.update_payment_status, name='update_payment_status'),


    
    
    # Admin features
    path('add-category/', views.add_category, name='add_category'),
    path('create-teacher/', views.create_teacher_account, name='create_teacher'),
    
    # Other
    path('test/', views.test_view, name='test'),
    
]