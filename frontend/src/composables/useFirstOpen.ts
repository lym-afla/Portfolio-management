import { readonly, ref, watch, type Ref } from 'vue'

// Retain the component after first use: closing an import must not end its session.
export function useFirstOpen(open: Ref<boolean>) {
  const mounted = ref(open.value)
  watch(open, value => { if (value) mounted.value = true }, { flush: 'sync' })
  return readonly(mounted)
}
