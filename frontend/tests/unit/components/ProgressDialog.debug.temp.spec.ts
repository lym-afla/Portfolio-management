import { beforeAll, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import ProgressDialog from '@/components/dialogs/ProgressDialog.vue'

const vuetify = createVuetify({ components, directives })

describe('debug', () => {
  beforeAll(() => {
    const viewport = {
      width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
    }
    Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
  })

  it('dumps html', () => {
    const wrapper = mount(ProgressDialog, {
      props: { modelValue: true, title: 'T', progress: 50, current: 5, total: 10, currentMessage: 'msg' },
      global: { plugins: [vuetify, createPinia()], stubs: { teleport: true } },
      attachTo: document.body,
    })
    console.log('HTML>', wrapper.html().slice(0, 900))
    console.log('HAS LABEL>', wrapper.find('[data-testid="import-progress-label"]').exists())
    console.log('HAS BAR>', wrapper.find('.v-progress-linear').exists())
    wrapper.unmount()
  })
})
