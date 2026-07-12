module.exports = {
  env: {
    node: true,
    browser: true,
  },
  // vitest globals (describe/it/expect/vi/etc.) are provided via globals: true
  // in vite.config.js; add them as globals for eslint.
  globals: {
    describe: 'readonly',
    it: 'readonly',
    test: 'readonly',
    expect: 'readonly',
    beforeAll: 'readonly',
    afterAll: 'readonly',
    beforeEach: 'readonly',
    afterEach: 'readonly',
    vi: 'readonly',
  },
}
