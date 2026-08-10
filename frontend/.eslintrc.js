module.exports = {
    root: true,
    env: {
      node: true,
      browser: true,
      es2021: true
    },
    globals: {
      // Vue 3 <script setup> compiler macros — globally available, not imported.
      defineProps: 'readonly',
      defineEmits: 'readonly',
      defineExpose: 'readonly',
      defineOptions: 'readonly'
    },
    extends: [
      'plugin:vue/vue3-essential',
      'eslint:recommended',
      'prettier'
    ],
    parserOptions: {
      ecmaVersion: 2021,
      sourceType: 'module'
    },
    rules: {
      'no-console': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
      'no-debugger': process.env.NODE_ENV === 'production' ? 'warn' : 'off',
      'vue/multi-word-component-names': 'off',
      'vue/no-v-html': 'off',
      'vue/require-default-prop': 'off',
      'vue/require-prop-types': 'off',
      'vue/no-multiple-template-root': 'off',
      'vue/html-self-closing': ['error', {
        html: {
          void: 'always',
          normal: 'always',
          component: 'always'
        }
      }],
      'no-unused-vars': ['warn', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_'
      }]
    }
  }
