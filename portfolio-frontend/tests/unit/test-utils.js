// Creates a stub for a Vuetify component
const createVuetifyStub = (name) => ({
  template: `<${name.includes('v-') ? 'div' : name} class="${name}"><slot /></${name.includes('v-') ? 'div' : name}>`
})

// Special cases for form elements and components that need specific behavior
const specialStubs = {
  'v-form': {
    template: '<form class="v-form" ref="form"><slot /></form>',
    methods: {
      validate: () => true
    }
  },
  'v-text-field': {
    template: '<input class="v-text-field" />'
  },
  'v-select': {
    template: '<select class="v-select"><slot /></select>'
  },
  'v-checkbox': {
    template: '<input type="checkbox" class="v-checkbox" />'
  },
  'v-radio': {
    template: '<input type="radio" class="v-radio" />'
  },
  'v-radio-group': {
    template: '<div class="v-radio-group"><slot /></div>'
  },
  'v-switch': {
    template: '<input type="checkbox" class="v-switch" />'
  },
  'v-textarea': {
    template: '<textarea class="v-textarea"></textarea>'
  },
  transition: true
}

// Core Vuetify components that need stubs
const vuetifyComponents = [
  // Layout
  'v-app',
  'v-main',
  'v-container',
  'v-row',
  'v-col',
  'v-spacer',
  
  // Navigation
  'v-list',
  'v-list-item',
  'v-list-item-title',
  'v-list-item-subtitle',
  
  // Components
  'v-card',
  'v-card-title',
  'v-card-text',
  'v-card-actions',
  'v-card-subtitle',
  'v-card-item',
  'v-dialog',
  'v-btn',
  'v-icon',
  'v-chip',
  'v-tooltip',
  'v-menu',
  'v-overlay',
  
  // Data display
  'v-expansion-panels',
  'v-expansion-panel',
  'v-expansion-panel-title',
  'v-expansion-panel-text',
  'v-expand-transition',
  'v-fade-transition',
  'v-avatar',
  
  // Feedback
  'v-progress-linear',
  'v-alert',
  'v-snackbar',
  
  // Forms
  'v-form',
  'v-text-field',
  'v-select',
  'v-checkbox',
  'v-radio',
  'v-radio-group',
  'v-switch',
  'v-textarea',
  'v-slider',
  'v-file-input'
]

// Generate stubs for all Vuetify components
export function generateVuetifyStubs() {
  const stubs = vuetifyComponents.reduce((acc, componentName) => {
    acc[componentName] = specialStubs[componentName] || createVuetifyStub(componentName)
    return acc
  }, {})

  return { ...stubs, ...specialStubs }
} 