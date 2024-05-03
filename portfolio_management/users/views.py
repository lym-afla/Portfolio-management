from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views import generic
from .forms import SignUpForm, UserProfileForm, UserSettingsForm
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.contrib.auth import authenticate, login
from django.contrib import messages
from utils import effective_current_date

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
            'To': str(effective_current_date),
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
    settings_form = UserSettingsForm(instance=user)

    if request.method == 'POST':
        settings_form = UserSettingsForm(request.POST, instance=user)
        if settings_form.is_valid():
            settings_form.save()

            # After saving, update the session data
            request.session['chart_settings'] = {
                'frequency': user.chart_frequency,
                'timeline': user.chart_timeline,
                'To': str(effective_current_date),
                'breakdown': user.NAV_barchart_default_breakdown,
            }
            request.session['default_currency'] = user.default_currency
            # request.session['default_currency_for_all_data'] = user.use_default_currency_for_all_data
            request.session['digits'] = user.digits

            return JsonResponse({'success': True}, status=200)
        else:
            print(f"profile page: {settings_form.errors}")
            return JsonResponse({'errors': settings_form.errors}, status=400)

    return render(request, 'users/profile.html', {'user': user, 'settings_form': settings_form})

@login_required
def edit_profile(request):
    user = request.user
    profile_form = UserProfileForm(instance=user)
    print(f"users.views.py. {profile_form}")

    if request.method == 'POST':
        profile_form = UserProfileForm(request.POST, instance=user)
        if profile_form.is_valid():
            print(f"Printing profile form from profile {profile_form}")
            profile_form.save()
            return redirect('users:profile')

    return render(request, 'users/profile_edit.html', {'profile_form': profile_form})

def reset_password(u, password):
    try:
        user = get_user_model().objects.get(username=u)
    except:
        return "User could not be found"
    user.set_password(password)
    user.save()
    return "Password has been changed successfully"
