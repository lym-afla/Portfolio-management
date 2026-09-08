import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import vue from 'eslint-plugin-vue'
import globals from 'globals'
import tseslint from 'typescript-eslint'

const sourceFiles = ['src/**/*.{js,ts,vue}']
const testFiles = ['tests/**/*.{js,ts}']
const toolFiles = ['scripts/**/*.mjs', 'tests/browser/**/*.mjs']

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'src/types/api.d.ts',
      'tests/browser/artifacts/**',
    ],
  },
  {
    ...js.configs.recommended,
    files: [...sourceFiles, ...testFiles, ...toolFiles],
  },
  ...tseslint.configs.recommended.map((config) => ({
    ...config,
    files: ['src/**/*.ts', 'tests/**/*.ts', '**/*.vue'],
  })),
  ...vue.configs['flat/essential'].map((config) => ({
    ...config,
    files: ['**/*.vue'],
  })),
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
  },
  {
    files: sourceFiles,
    languageOptions: {
      globals: globals.browser,
    },
  },
  {
    files: testFiles,
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.vitest,
      },
    },
  },
  {
    files: toolFiles,
    languageOptions: {
      globals: globals.node,
    },
  },
  {
    files: [...sourceFiles, ...testFiles, ...toolFiles],
    plugins: {
      '@typescript-eslint': tseslint.plugin,
    },
    rules: {
      'no-console': 'off',
      'no-debugger': 'off',
      'no-undef': 'error',
      'no-empty': 'warn',
      'prefer-const': 'warn',
      'preserve-caught-error': 'warn',
      '@typescript-eslint/no-explicit-any': 'off',
      'vue/multi-word-component-names': 'off',
      'vue/no-v-html': 'off',
      'vue/require-default-prop': 'off',
      'vue/require-prop-types': 'off',
      'vue/no-multiple-template-root': 'off',
      'vue/html-self-closing': [
        'error',
        {
          html: {
            void: 'always',
            normal: 'always',
            component: 'always',
          },
        },
      ],
    },
  },
  {
    files: ['src/**/*.js', 'tests/**/*.js', ...toolFiles],
    rules: {
      'no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
        },
      ],
    },
  },
  {
    files: ['src/**/*.ts', 'tests/**/*.ts', '**/*.vue'],
    rules: {
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
        },
      ],
    },
  },
  prettier,
)
