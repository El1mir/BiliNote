import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // `({ node: _node, ...props })` is how a react-markdown renderer drops the
      // hast node before spreading the rest onto a DOM element. The omitted
      // binding is the whole point, so unused rest siblings are not reported.
      '@typescript-eslint/no-unused-vars': ['error', { ignoreRestSiblings: true }],
    },
  },
  {
    // Ambient declaration shims re-declare a namespace member with an empty body on
    // purpose: the emptiness is what makes it a pure alias of its supertype, and an
    // `interface` (rather than a `type`) is required so that any other library
    // declaring the same global namespace can still merge into it.
    files: ['src/types/**/*.d.ts'],
    rules: {
      '@typescript-eslint/no-empty-object-type': 'off',
    },
  }
)
