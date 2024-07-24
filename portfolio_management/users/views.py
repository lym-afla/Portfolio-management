import json
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views import generic

from common.forms import DashboardForm
from common.models import Brokers
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
        dashboard_form = DashboardForm(request.POST, instance=user)
        if dashboard_form.is_valid():
            # Process the form data
            request.session['effective_current_date'] = dashboard_form.cleaned_data['table_date'].isoformat()
            # request.session['effective_current_date'] = effective_current_date.strftime('%Y-%m-%d')
            print("views. users. 120", request.session['effective_current_date'])
            
            # Save new parameters to user setting
            user.default_currency = dashboard_form.cleaned_data['default_currency']
            user.digits = dashboard_form.cleaned_data['digits']
            selected_broker_ids = [dashboard_form.cleaned_data['custom_brokers']]
            # broker_name = dashboard_form.cleaned_data['custom_brokers']
            # print("users. views. 126", broker_name)
            # selected_broker_ids = [broker.id for broker in Brokers.objects.filter(investor=user, name=broker_name)]
            user.custom_brokers = selected_broker_ids
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
            broker_name = data.get('broker_name')

            print("users. 139", broker_name, data)
            if broker_name:

                selected_broker_ids = [broker.id for broker in Brokers.objects.filter(investor=user, name=broker_name)]
                print("users. 140", selected_broker_ids)
                if selected_broker_ids is not None and len(selected_broker_ids) > 0:
                    user.custom_brokers = selected_broker_ids
                    user.save()

                return JsonResponse({'ok': True})
            else:
                return JsonResponse({'ok': False, 'error': 'Broker name not provided'})
        except json.JSONDecodeError:
            return JsonResponse({'ok': False, 'error': 'Invalid JSON data'})
        
    return JsonResponse({'ok': False, 'error': 'Invalid request method'})

    # # Redirect to the same page to refresh it
    # return redirect(request.META.get('HTTP_REFERER'))

