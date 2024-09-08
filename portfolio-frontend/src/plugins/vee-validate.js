import { defineRule, configure } from 'vee-validate';
import { required, email, min, max } from '@vee-validate/rules';
import { localize } from '@vee-validate/i18n';

// Define the rules you want to use
defineRule('required', required);
defineRule('email', email);
defineRule('min', min);
defineRule('max', max);

// Configure Vee-Validate
configure({
  generateMessage: localize('en', {
    messages: {
      required: '{field} is required',
      email: '{field} must be a valid email',
      min: '{field} must be at least 0:{min} characters',
      max: '{field} must not be more than 0:{max} characters',
    },
  }),
});