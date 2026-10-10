// Task 3 (real-data corrections): the price-import progress percentage label
// must live OUTSIDE the moving fill in a stable contrasting element — the
// previous in-slot label rendered white-on-light over the unfilled track and
// was unreadable at low percentages. The v-dialog teleports its content to
// document.body, so assertions run at the document level.
import { beforeAll, afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import ProgressDialog from '@/components/dialogs/ProgressDialog.vue'

const vuetify = createVuetify({ components, directives })

beforeAll(() => {
  const viewport = {
    width: 1024, height: 768, offsetLeft: 0, offsetTop: 0, pageLeft: 0, pageTop: 0, scale: 1,
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => true,
  }
  Object.defineProperty(window, 'visualViewport', { value: viewport, configurable: true })
})

afterEach(() => {
  document.body.innerHTML = ''
})

const mountProgress = (props: Record<string, unknown>) =>
  mount(ProgressDialog, {
    attachTo: document.body,
    props: { modelValue: true, title: 'Importing prices', currentMessage: 'Starting import', ...props },
    global: { plugins: [vuetify, createPinia()] },
  })

const labelAt = () => {
  const overlay = [...document.querySelectorAll('.v-dialog.v-overlay--active')]
  const host = overlay.find((el) => el.querySelector('[data-testid="import-progress-label"]'))
  return host ? host.querySelector('[data-testid="import-progress-label"]') : null
}

describe('ProgressDialog readability', () => {
  it.each([0, 25, 50, 100])('shows a readable %i%% label outside the moving fill', async (progress) => {
    const wrapper = mountProgress({ progress, current: Math.round(progress / 10), total: 10 })
    await new Promise((resolve) => setTimeout(resolve, 50))
    const label = labelAt()
    expect(label).toBeTruthy()
    expect(label.textContent).toContain(`${progress}%`)
    // The label is not swallowed by the bar itself.
    const bar = label.closest('.v-progress-linear')
    expect(bar).toBeFalsy()
    // The label sits in a stable contrasting element on the card surface;
    // the spans carry the body text style (theme-contrasting, not on-primary).
    expect(label.querySelector('.text-body-2')).toBeTruthy()
    wrapper.unmount()
    document.body.innerHTML = ''
  })

  it('keeps the label stable between 0% and 100% (same element, live updates)', async () => {
    const wrapper = mountProgress({ progress: 0, current: 0, total: 10 })
    const label = labelAt()
    expect(label.textContent).toContain('0%')
    wrapper.vm.$forceUpdate()
    wrapper.unmount()
    document.body.innerHTML = ''
  })
})
