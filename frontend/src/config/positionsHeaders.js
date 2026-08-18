export const openPositionsHeaders = [
  { title: 'Type', key: 'type', align: 'start', sortable: true },
  { title: 'Name', key: 'name', align: 'start', sortable: true },
  { title: 'Currency', key: 'currency', align: 'end', sortable: true },
  { title: 'Position', key: 'current_position', align: 'end', sortable: true },
  {
    title: 'Entry',
    key: 'entry',
    align: 'end',
    sortable: false,
    children: [
      { title: 'Date', key: 'investment_date', align: 'end', sortable: true },
      { title: 'Price', key: 'entry_price', align: 'end', sortable: true },
      { title: 'Value', key: 'entry_value', align: 'end', sortable: true },
    ],
  },
  {
    title: 'Current',
    key: 'current',
    align: 'end',
    sortable: false,
    children: [
      { title: 'Price', key: 'current_price', align: 'end', sortable: true },
      { title: 'Value', key: 'current_value', align: 'end', sortable: true },
      { title: 'Share %', key: 'share_of_portfolio', align: 'end', sortable: true, class: 'font-italic',
        description: "Current market value of the position as a share of the portfolio's total NAV." },
      { title: 'Price Δ %', key: 'price_change_percentage', align: 'end', sortable: true, class: 'font-italic',
        description: 'Change between entry price and current price, in percent.' },
      { title: 'Realized G/L', key: 'realized_gl', align: 'end', sortable: true },
      { title: 'Unrealized G/L', key: 'unrealized_gl', align: 'end', sortable: true },
      { title: 'Cap. Distr.', key: 'capital_distribution', align: 'end', sortable: true },
      { title: 'Cap. Distr. %', key: 'capital_distribution_percentage', align: 'end', sortable: true, class: 'font-italic' },
      { title: 'Commission', key: 'commission', align: 'end', sortable: true },
      { title: 'Commission %', key: 'commission_percentage', align: 'end', sortable: true, class: 'font-italic' },
      { title: 'Total Return', key: 'total_return_amount', align: 'end', sortable: true },
      { title: 'Total Return %', key: 'total_return_percentage', align: 'end', sortable: true, class: 'font-italic',
        description: 'Total return incl. capital distributions and after commissions, relative to entry value.' },
      { title: 'IRR', key: 'irr', align: 'end', sortable: true, class: 'font-italic',
        description: 'Money-weighted internal rate of return since the position was opened.' },
    ],
  },
]

export const closedPositionsHeaders = [
  { title: 'Type', key: 'type', align: 'start', sortable: false },
  { title: 'Name', key: 'name', align: 'start', sortable: true },
  { title: 'Currency', key: 'currency', align: 'end', sortable: true },
  {
    title: 'Entry',
    key: 'entry',
    align: 'end',
    sortable: false,
    children: [
      { title: 'Date', key: 'investment_date', align: 'end', sortable: true },
      { title: 'Value', key: 'entry_value', align: 'end', sortable: true },
    ],
  },
  {
    title: 'Exit',
    key: 'exit',
    align: 'end',
    sortable: false,
    children: [
      { title: 'Date', key: 'exit_date', align: 'end', sortable: true },
      { title: 'Value', key: 'exit_value', align: 'end', sortable: true },
    ],
  },
  {
    title: 'Realized gain/(loss)',
    key: 'realized',
    align: 'end',
    sortable: false,
    children: [
      { title: 'Amount', key: 'realized_gl', align: 'end', sortable: true },
      { title: '%', key: 'price_change_percentage', align: 'end', sortable: true, class: 'font-italic' },
    ],
  },
  {
    title: 'Capital distribution',
    key: 'capital',
    align: 'end',
    sortable: false,
    children: [
      { title: 'Amount', key: 'capital_distribution', align: 'end', sortable: true },
      { title: '%', key: 'capital_distribution_percentage', align: 'end', sortable: true, class: 'font-italic' },
    ],
  },
  {
    title: 'Commission',
    key: 'commission',
    align: 'end',
    sortable: false,
    children: [
      { title: 'Amount', key: 'commission', align: 'end', sortable: true },
      { title: '%', key: 'commission_percentage', align: 'end', sortable: true, class: 'font-italic' },
    ],
  },
  {
    title: 'Total return',
    key: 'total',
    align: 'end',
    sortable: false,
    children: [
      { title: 'Amount', key: 'total_return_amount', align: 'end', sortable: true },
      { title: '%', key: 'total_return_percentage', align: 'end', sortable: true, class: 'font-italic',
        description: 'Total return incl. capital distributions and after commissions, relative to entry value.' },
      { title: 'IRR', key: 'irr', align: 'end', sortable: true, class: 'font-italic',
        description: 'Money-weighted internal rate of return since the position was opened.' },
    ],
  },
]

export const flattenHeaders = (headers) =>
  headers.flatMap((h) => (h.children ? flattenHeaders(h.children) : [h]))

export const openPercentageColumns = [
  'share_of_portfolio', 'price_change_percentage',
  'capital_distribution_percentage', 'commission_percentage',
  'total_return_percentage', 'irr',
]
export const closedPercentageColumns = [
  'price_change_percentage', 'capital_distribution_percentage',
  'commission_percentage', 'total_return_percentage', 'irr',
]

// "Analyst default" — identity + entry + current value + return columns.
export const openDefaultVisibleKeys = [
  'type', 'name', 'currency', 'current_position',
  'investment_date', 'entry_price', 'entry_value',
  'current_price', 'current_value', 'share_of_portfolio',
  'total_return_amount', 'total_return_percentage', 'irr',
]
export const closedDefaultVisibleKeys = null // closed table is narrow enough: all visible
