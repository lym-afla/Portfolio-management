import json
from django import forms
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views import generic
from django.utils import timezone

from common.forms import DashboardForm, DashboardForm_old_setup
from common.models import Brokers
from constants import BROKER_GROUPS, CURRENCY_CHOICES, NAV_BARCHART_CHOICES
from .forms import SignUpForm, UserProfileForm, UserSettingsForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib.auth import authenticate, login
from django.contrib import messages

class SignUpView(generic.CreateView):
    form_class = SignUpForm
    success_url = reverse_lazy('login')
    template_name = 'registration/signup.html'

def user_login(request):
    print("Running loging function")
    # Your login logic here
    username = request.POST['username']
    password = request.POST['password']
    user = authenticate(request, username=username, password=password)
    
    if user is not None:
        login(request, user)
        
        # Store user-specific settings in the session
        request.session['chart_settings'] = {
            'frequency': user.chart_frequency,
            'timeline': user.chart_timeline,
            'breakdown': user.NAV_barchart_default_breakdown,
        }
        request.session['default_currency'] = user.default_currency
        request.session['digits'] = user.digits
        
        # Redirect to a success page.
        print('redirecting to dashboard')
        return redirect('dashboard:dashboard')
    else:
        # Add an error message to be displayed in the template
        messages.error(request, 'Invalid login credentials. Please try again.')
    return render(request, 'registration/login.html')

@login_required
def profile(request):

    user = request.user

    if request.method == 'POST':
        settings_form = UserSettingsForm(request.POST, instance=user)
        if settings_form.is_valid():
            settings_form.save()
            # print("users. 56", settings_form)

            # After saving, update the session data
            request.session['chart_settings'] = {
                'frequency': user.chart_frequency,
                'timeline': user.chart_timeline,
                'breakdown': user.NAV_barchart_default_breakdown,
            }
            request.session['default_currency'] = user.default_currency
            # request.session['default_currency_for_all_data'] = user.use_default_currency_for_all_data
            request.session['digits'] = user.digits
            request.session['custom_brokers'] = user.custom_brokers

            return JsonResponse({'success': True}, status=200)
        else:
            print(f"profile page: {settings_form.errors}")
            return JsonResponse({'errors': settings_form.errors}, status=400)
    else:
        settings_form = UserSettingsForm(instance=user)
        print(f"DEBUG: user.custom_brokers in GET request = {user.custom_brokers}")
        
    user_info = [
        {"label": "Username", "value": user.username},
        {"label": "First Name", "value": user.first_name},
        {"label": "Last Name", "value": user.last_name},
        {"label": "Email", "value": user.email},
    ]

    return render(request, 'profile.html', {'user_info': user_info, 'settings_form': settings_form})

@login_required
def edit_profile(request):
    user = request.user
    profile_form = UserProfileForm(instance=user)
    # print(f"users.views.py. {profile_form}")

    if request.method == 'POST':
        profile_form = UserProfileForm(request.POST, instance=user)
        if profile_form.is_valid():
            # print(f"Printing profile form from profile {profile_form}")
            profile_form.save()
            return redirect('users:profile')

    return render(request, 'profile_edit.html', {'profile_form': profile_form})

def reset_password(u, password):
    try:
        user = get_user_model().objects.get(username=u)
    except:
        return "User could not be found"
    user.set_password(password)
    user.save()
    return "Password has been changed successfully"

@login_required
def update_from_dashboard_form(request):

    # global effective_current_date

    user = request.user

    # In case settings at the top menu are changed
    if request.method == "POST":
        dashboard_form = DashboardForm_old_setup(request.POST, instance=user)
        if dashboard_form.is_valid():
            # Process the form data
            request.session['effective_current_date'] = dashboard_form.cleaned_data['table_date'].isoformat()
            
            # Save new parameters to user setting
            user.default_currency = dashboard_form.cleaned_data['default_currency']
            user.digits = dashboard_form.cleaned_data['digits']
            user.custom_brokers = dashboard_form.cleaned_data['custom_brokers']
            user.save()
            # Redirect to the same page to refresh it
            return redirect(request.META.get('HTTP_REFERER'))
    return redirect('dashboard:dashboard')  # Redirect to home page if request method is not POST

@login_required
def update_data_for_broker(request):

    # In case settings at the top menu are changed
    if request.method == "POST":
        try:
            user = request.user

            data = json.loads(request.body.decode('utf-8'))
            broker_or_group_name = data.get('broker_or_group_name')

            print("users. 139", broker_or_group_name, data)
            if broker_or_group_name:

                user.custom_brokers = broker_or_group_name
                # user.custom_brokers = selected_broker_ids

                # if broker_name == 'All brokers':
                #     # selected_broker_ids = 'All'
                #     user.custom_brokers = Brokers.objects.filter(investor=user).values_list('id', flat=True)
                # else:
                #     selected_broker_ids = [broker.id for broker in Brokers.objects.filter(investor=user, name=broker_name)]
                # # print("users. 140", selected_broker_ids)
                # # if selected_broker_ids is not None and len(selected_broker_ids) > 0:
                #     user.custom_brokers = selected_broker_ids
                
                user.save()

                return JsonResponse({'ok': True})
            else:
                return JsonResponse({'ok': False, 'error': 'Broker name not provided'})
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON data'})
        
    return JsonResponse({'ok': False, 'error': 'Invalid request method'})

    # # Redirect to the same page to refresh it
    # return redirect(request.META.get('HTTP_REFERER'))

from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from .serializers import UserSerializer
from django.contrib.auth import authenticate, get_user_model, logout
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password

import logging

logger = logging.getLogger(__name__)

class RegisterView(APIView):
    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User registered successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CustomObtainAuthToken(ObtainAuthToken):
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data,
                                           context={'request': request})
        if serializer.is_valid():
            user = serializer.validated_data['user']
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user_id': user.pk,
                'email': user.email
            })
        else:
            errors = {}
            username = request.data.get('username')
            password = request.data.get('password')

            if not username:
                errors['username'] = ['This field is required.']
            if not password:
                errors['password'] = ['This field is required.']

            if username and password:
                User = get_user_model()
                try:
                    user = User.objects.get(username=username)
                    if not user.check_password(password):
                        errors['password'] = ['Incorrect password.']
                except User.DoesNotExist:
                    errors['username'] = ['User with this username does not exist.']

            # Validate password complexity only if a password is provided
            if password:
                try:
                    validate_password(password)
                except ValidationError as e:
                    errors['password'] = list(e.messages)

            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        user.delete()
        return Response({"message": "Account successfully deleted"}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def edit_profile_api(request):
    user = request.user
    profile_form = UserProfileForm(request.data, instance=user)
    if profile_form.is_valid():
        profile_form.save()
        return Response({'success': True})
    return Response({
        'success': False,
        'errors': profile_form.errors
    }, status=400)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile_api(request):
    user = request.user
    user_info = [
        {"label": "Username", "value": user.username},
        {"label": "First Name", "value": user.first_name},
        {"label": "Last Name", "value": user.last_name},
        {"label": "Email", "value": user.email},
    ]
    return Response({'user_info': user_info})

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def user_settings_api(request):
    user = request.user
    if request.method == 'POST':
        settings_form = UserSettingsForm(request.data, instance=user)
        if settings_form.is_valid():
            settings_form.save()
            print("views. users. 284", settings_form)
            return Response({'success': True})
        return Response({
            'success': False,
            'errors': settings_form.errors
        }, status=400)
    else:
        settings = {
            'default_currency': user.default_currency,
            'use_default_currency_where_relevant': user.use_default_currency_where_relevant,
            'chart_frequency': user.chart_frequency,
            'chart_timeline': user.chart_timeline,
            'NAV_barchart_default_breakdown': user.NAV_barchart_default_breakdown,
            'digits': user.digits,
            'custom_brokers': user.custom_brokers,
        }
        return Response(settings)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_settings_choices_api(request):
    user = request.user
    form = UserSettingsForm(instance=user)
    choices = {
        'currency_choices': CURRENCY_CHOICES,
        'frequency_choices': UserSettingsForm.FREQUENCY_CHOICES,
        'timeline_choices': UserSettingsForm.TIMELINE_CHOICES,
        'nav_breakdown_choices': NAV_BARCHART_CHOICES,
        'broker_choices': form.get_broker_choices(user),
    }
    return Response(choices)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password_api(request):
    user = request.user
    old_password = request.data.get('old_password')
    new_password1 = request.data.get('new_password1')
    new_password2 = request.data.get('new_password2')

    if not user.check_password(old_password):
        return Response({'error': 'Incorrect old password'}, status=400)

    if new_password1 != new_password2:
        return Response({'error': 'New passwords do not match'}, status=400)

    user.set_password(new_password1)
    user.save()
    return Response({'success': True})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_api(request):
    logout(request)
    return Response({'success': True})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def verify_token_api(request):
    return Response({'valid': True})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_broker_choices_api(request):
    user = request.user
    form = UserSettingsForm(instance=user)
    broker_choices = form.get_broker_choices(user)
    
    return Response({
        'options': broker_choices,
        'custom_brokers': user.custom_brokers
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_user_broker_api(request):
    user = request.user
    broker_or_group_name = request.data.get('broker_or_group_name')
    
    if broker_or_group_name:
        user.custom_brokers = broker_or_group_name
        user.save()
        return Response({'ok': True})
    else:
        return Response({'ok': False, 'error': 'Broker or group name not provided'}, status=400)

from django.views.decorators.csrf import ensure_csrf_cookie

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@ensure_csrf_cookie
def update_user_settings_from_dashboard(request):
    logger.info(f"Received data: {request.data}")
    user = request.user
    form = DashboardForm(request.data, instance=user)
    
    if form.is_valid():
        form.save()
        table_date = form.cleaned_data['table_date']
        request.session['effective_current_date'] = table_date.isoformat()
        # request.session.modified = True
        print(f"Settings updated. New date: {table_date} for {request.user.username}")
        
        logger.info(f"Updated effective_current_date for user {user.id}: {request.session['effective_current_date']}")
        
        logger.info(f"Session before save: {dict(request.session)}")
        # request.session.save()
        logger.info(f"Session after save: {dict(request.session)} for {request.user.username}")

        return Response({
            'success': True,
            'message': 'Settings updated successfully',
            'data': {
                'default_currency': user.default_currency,
                'table_date': request.session['effective_current_date'],
                'digits': user.digits,
            }
        })
    else:
        logger.error(f"Form validation failed for user {user.id}: {form.errors}")
        return Response({
            'success': False,
            'errors': form.errors
        }, status=400)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_dashboard_settings(request):
    user = request.user
    form = DashboardForm(instance=user)
    
    form_fields = []
    for field_name, field in form.fields.items():
        field_data = {
            'name': field_name,
            'label': field.label,
            'type': 'text',  # default type
        }
        
        if isinstance(field, forms.DateField):
            field_data['type'] = 'date'
        elif isinstance(field, forms.IntegerField):
            field_data['type'] = 'number'
        elif isinstance(field, forms.ChoiceField):
            field_data['type'] = 'select'
            field_data['choices'] = [{'text': choice[1], 'value': choice[0]} for choice in field.choices]
        
        form_fields.append(field_data)
    
    data = {
        'form_fields': form_fields,
    }
    
    # Add current values
    for field in form_fields:
        if field['name'] == 'table_date':
            # Use the session value or current date for table_date
            data[field['name']] = request.session.get('effective_current_date')#, timezone.now().date().isoformat())
        elif field['type'] == 'select':
            current_value = getattr(user, field['name'])
            choices_dict = {choice['value']: choice['text'] for choice in field['choices']}
            data[field['name']] = {
                'value': current_value,
                'text': choices_dict.get(current_value, current_value)  # Fallback to the value if text is not found
            }
        else:
            data[field['name']] = getattr(user, field['name'])
    
    return Response(data)