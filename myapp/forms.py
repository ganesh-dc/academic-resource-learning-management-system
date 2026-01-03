from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User, Resource, Category, Feedback, Payment
from django.core.exceptions import ValidationError

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=User.ROLE_CHOICES)
    
    class Meta:
        model = User
        fields = ['username', 'email', 'role', 'password1', 'password2']

class ResourceUploadForm(forms.ModelForm):
    class Meta:
        model = Resource
        fields = ['title', 'description', 'category', 'file', 'is_premium', 'price']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
        }

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
        }

class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ['message', 'rating']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Enter your feedback...'}),
        }

class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ['amount', 'status']
class TeacherCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'teacher@example.com'
        })
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Choose a username'
            }),
        }
        help_texts = {
            'username': 'Maximum 150 characters. Letters, numbers, and @ . + - _ only.',
        }
        error_messages = {
            'username': {
                'max_length': "Username is too long (maximum 150 characters).",
                'required': "Username is required.",
            },
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Style password fields
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Enter password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Confirm password'
        })
        
        # Remove or customize the UserAttributeSimilarityValidator
        for validator in self.fields['password1'].validators:
            if hasattr(validator, 'user_attributes'):
                # Make the similarity check less strict
                validator.max_similarity = 0.9  # Default is 0.7 (0.9 = more lenient)
                break
        
        # Customize username field help text
        self.fields['username'].help_text = 'Maximum 150 characters. Letters, numbers, and @ . + - _ only.'
        
        # Customize username field validators
        self.fields['username'].validators = [
            v for v in self.fields['username'].validators 
            if not hasattr(v, 'message') or '150 characters' not in v.message
        ]
        
        # Add custom validator with better message
        from django.core.validators import MaxLengthValidator, RegexValidator
        self.fields['username'].validators.append(
            MaxLengthValidator(
                150, 
                message='Username is too long (maximum 150 characters).'
            )
        )
        self.fields['username'].validators.append(
            RegexValidator(
                r'^[\w.@+-]+$',
                message='Username can only contain letters, numbers, and @ . + - _ characters.'
            )
        )
    
    def clean_username(self):
        username = self.cleaned_data.get('username')
        
        if username:
            # Check length
            if len(username) > 150:
                raise ValidationError('Username is too long (maximum 150 characters).')
            
            # Check valid characters
            import re
            if not re.match(r'^[\w.@+-]+$', username):
                raise ValidationError('Username can only contain letters, numbers, and @ . + - _ characters.')
            
            # Check if username exists
            if User.objects.filter(username=username).exists():
                raise ValidationError('This username is already taken. Please choose a different one.')
        
        return username
    
    def clean_password1(self):
        password1 = self.cleaned_data.get('password1')
        username = self.cleaned_data.get('username', '')
        
        # Custom validation - more lenient than Django's default
        if username and password1:
            # Check if password is exactly the same as username
            if password1.lower() == username.lower():
                raise ValidationError('Password should not be identical to username.')
            
            # Check if password contains username (partial match)
            if username.lower() in password1.lower() and len(username) > 3:
                raise ValidationError('Password should not contain your username.')
        
        return password1
    
    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        # Custom password match validation with better error message
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'Passwords do not match.')
        
        return cleaned_data
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.role = 'teacher'
        user.is_active = True
        
        if commit:
            user.save()
        return user