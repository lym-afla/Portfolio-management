import { h } from "vue"
import { aliases, mdi } from "vuetify/iconsets/mdi-svg"
type IconValue = typeof aliases.close
import { mdiAccountCircle, mdiAccountGroup, mdiAlertCircle, mdiApi, mdiApps, mdiArrowLeft, mdiArrowRightBold, mdiBank, mdiBankMinus, mdiBankPlus, mdiBitcoin, mdiCalendar, mdiCalendarRange, mdiCancel, mdiCash, mdiCashMultiple, mdiChartBox, mdiChartLine, mdiCheck, mdiCheckAll, mdiCheckCircle, mdiCheckCircleOutline, mdiChevronLeft, mdiChevronRight, mdiClipboardCheck, mdiClipboardRemove, mdiClose, mdiCloseCircle, mdiCog, mdiCounter, mdiCurrencyUsd, mdiCurrencyUsdOff, mdiDatabase, mdiDatabaseImport, mdiDelete, mdiFileDocumentOutline, mdiFileUpload, mdiImport, mdiInformation, mdiKeyRemove, mdiLinkVariant, mdiLockCheck, mdiMagnify, mdiMenu, mdiMonitorDashboard, mdiNumeric, mdiOfficeBuilding, mdiPencil, mdiPercent, mdiPlus, mdiPlusCircle, mdiSwapHorizontal, mdiTableColumn, mdiUpdate, mdiUpload, mdiHelpCircleOutline } from "@mdi/js"

export const iconRegistry: Record<string, string> = {
  'mdi-account-circle': mdiAccountCircle,
  'mdi-account-group': mdiAccountGroup,
  'mdi-alert-circle': mdiAlertCircle,
  'mdi-api': mdiApi,
  'mdi-apps': mdiApps,
  'mdi-arrow-left': mdiArrowLeft,
  'mdi-arrow-right-bold': mdiArrowRightBold,
  'mdi-bank': mdiBank,
  'mdi-bank-minus': mdiBankMinus,
  'mdi-bank-plus': mdiBankPlus,
  'mdi-bitcoin': mdiBitcoin,
  'mdi-calendar': mdiCalendar,
  'mdi-calendar-range': mdiCalendarRange,
  'mdi-cancel': mdiCancel,
  'mdi-cash': mdiCash,
  'mdi-cash-multiple': mdiCashMultiple,
  'mdi-chart-box': mdiChartBox,
  'mdi-chart-line': mdiChartLine,
  'mdi-check': mdiCheck,
  'mdi-check-all': mdiCheckAll,
  'mdi-check-circle': mdiCheckCircle,
  'mdi-check-circle-outline': mdiCheckCircleOutline,
  'mdi-chevron-left': mdiChevronLeft,
  'mdi-chevron-right': mdiChevronRight,
  'mdi-clipboard-check': mdiClipboardCheck,
  'mdi-clipboard-remove': mdiClipboardRemove,
  'mdi-close': mdiClose,
  'mdi-close-circle': mdiCloseCircle,
  'mdi-cog': mdiCog,
  'mdi-counter': mdiCounter,
  'mdi-currency-usd': mdiCurrencyUsd,
  'mdi-currency-usd-off': mdiCurrencyUsdOff,
  'mdi-database': mdiDatabase,
  'mdi-database-import': mdiDatabaseImport,
  'mdi-delete': mdiDelete,
  'mdi-file-document-outline': mdiFileDocumentOutline,
  'mdi-file-upload': mdiFileUpload,
  'mdi-import': mdiImport,
  'mdi-information': mdiInformation,
  'mdi-key-remove': mdiKeyRemove,
  'mdi-link-variant': mdiLinkVariant,
  'mdi-lock-check': mdiLockCheck,
  'mdi-magnify': mdiMagnify,
  'mdi-menu': mdiMenu,
  'mdi-monitor-dashboard': mdiMonitorDashboard,
  'mdi-numeric': mdiNumeric,
  'mdi-office-building': mdiOfficeBuilding,
  'mdi-pencil': mdiPencil,
  'mdi-percent': mdiPercent,
  'mdi-plus': mdiPlus,
  'mdi-plus-circle': mdiPlusCircle,
  'mdi-swap-horizontal': mdiSwapHorizontal,
  'mdi-table-column': mdiTableColumn,
  'mdi-update': mdiUpdate,
  'mdi-upload': mdiUpload,
}

export function resolveAppIcon(icon: IconValue): IconValue {
  if (typeof icon !== 'string' || !icon.startsWith('mdi-')) return icon
  const path = iconRegistry[icon]
  if (path) return path
  if (import.meta.env.MODE === 'test') throw new Error(`Unknown icon: ${icon}`)
  if (import.meta.env.DEV) console.warn(`Unknown icon: ${icon}`)
  return mdiHelpCircleOutline
}

export const appIcons = {
  defaultSet: 'mdi',
  aliases,
  sets: { mdi: { component: (props: { icon: IconValue; tag: string }) => h(mdi.component, { ...props, icon: resolveAppIcon(props.icon) }) } },
}
