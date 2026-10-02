// Leaf metadata extensions (D4): every original leaf keeps its key/title/
// align/sortable contract and additionally carries groupId (lifecycle group),
// fullTitle (qualified standalone name for choosers, sort summaries and
// accessible labels), unitKind (identity | date | quantity | instrument-price |
// reporting-money | ratio), identity/pinned flags and a glossary description.
// reporting-money descriptions carry a {currency} placeholder that is resolved
// from the committed reporting currency by buildPositionView; instrument
// prices always stay in the security's trading currency (bonds: percent of
// nominal) and never follow the reporting currency.
export const openPositionsHeaders = [
  {
    title: 'Type', key: 'type', align: 'start', sortable: true,
    groupId: 'identity', fullTitle: 'Type', unitKind: 'identity', identity: true, pinned: true,
    description: 'Asset type of the security.',
  },
  {
    title: 'Name', key: 'name', align: 'start', sortable: true,
    groupId: 'identity', fullTitle: 'Security', unitKind: 'identity', identity: true, pinned: true,
    description: 'Security name; links to the security detail page.',
  },
  {
    title: 'Currency', key: 'currency', align: 'end', sortable: true,
    groupId: 'identity', fullTitle: 'Currency', unitKind: 'identity',
    description: 'Trading currency of the security.',
  },
  {
    title: 'Position', key: 'current_position', align: 'end', sortable: true,
    groupId: 'identity', fullTitle: 'Position', unitKind: 'quantity',
    description: 'Number of units currently held.',
  },
  {
    title: 'Entry',
    key: 'entry',
    align: 'end',
    sortable: false,
    children: [
      {
        title: 'Date', key: 'investment_date', align: 'end', sortable: true,
        groupId: 'entry', fullTitle: 'Entry date', unitKind: 'date',
        description: 'Date the position was opened.',
      },
      {
        title: 'Price', key: 'entry_price', align: 'end', sortable: true,
        groupId: 'entry', fullTitle: 'Entry price', unitKind: 'instrument-price',
        description: "Price paid per unit in the security's trading currency. Bond prices are quoted as a percentage of nominal value.",
      },
      {
        title: 'Value', key: 'entry_value', align: 'end', sortable: true,
        groupId: 'entry', fullTitle: 'Entry value', unitKind: 'reporting-money',
        description: 'Value of the initial investment in your reporting currency ({currency}).',
      },
    ],
  },
  {
    title: 'Current',
    key: 'current',
    align: 'end',
    sortable: false,
    children: [
      {
        title: 'Price', key: 'current_price', align: 'end', sortable: true,
        groupId: 'current', fullTitle: 'Current price', unitKind: 'instrument-price',
        description: "Latest price per unit in the security's trading currency. Bond prices are quoted as a percentage of nominal value.",
      },
      {
        title: 'Value', key: 'current_value', align: 'end', sortable: true,
        groupId: 'current', fullTitle: 'Current value', unitKind: 'reporting-money',
        description: 'Current market value of the position in your reporting currency ({currency}).',
      },
      { title: 'Share %', key: 'share_of_portfolio', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'current', fullTitle: 'Portfolio share %', unitKind: 'ratio',
        description: "Current market value of the position as a share of the portfolio's total NAV." },
      {
        title: 'Price Δ %', key: 'price_change_percentage', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'performance', fullTitle: 'Price change %', unitKind: 'ratio',
        description: 'Change between entry price and current price, in percent.',
      },
      {
        title: 'Realized G/L', key: 'realized_gl', align: 'end', sortable: true,
        groupId: 'performance', fullTitle: 'Realized G/L amount', unitKind: 'reporting-money',
        description: 'Realized gain or (loss) in your reporting currency ({currency}).',
      },
      {
        title: 'Unrealized G/L', key: 'unrealized_gl', align: 'end', sortable: true,
        groupId: 'performance', fullTitle: 'Unrealized G/L amount', unitKind: 'reporting-money',
        description: 'Unrealized gain or (loss) in your reporting currency ({currency}).',
      },
      {
        title: 'Cap. Distr.', key: 'capital_distribution', align: 'end', sortable: true,
        groupId: 'performance', fullTitle: 'Capital distribution amount', unitKind: 'reporting-money',
        description: 'Capital distributions received, in your reporting currency ({currency}).',
      },
      { title: 'Cap. Distr. %', key: 'capital_distribution_percentage', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'performance', fullTitle: 'Capital distribution %', unitKind: 'ratio',
        description: 'Capital distributions relative to entry value, in percent.' },
      {
        title: 'Commission', key: 'commission', align: 'end', sortable: true,
        groupId: 'performance', fullTitle: 'Commission amount', unitKind: 'reporting-money',
        description: 'Commissions paid, shown as negative amounts, in your reporting currency ({currency}).',
      },
      { title: 'Commission %', key: 'commission_percentage', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'performance', fullTitle: 'Commission %', unitKind: 'ratio',
        description: 'Commissions relative to entry value, in percent.' },
      {
        title: 'Total Return', key: 'total_return_amount', align: 'end', sortable: true,
        groupId: 'performance', fullTitle: 'Total return amount', unitKind: 'reporting-money',
        description: 'Total return including capital distributions and after commissions, in your reporting currency ({currency}).',
      },
      { title: 'Total Return %', key: 'total_return_percentage', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'performance', fullTitle: 'Total return %', unitKind: 'ratio',
        description: 'Total return incl. capital distributions and after commissions, relative to entry value.' },
      { title: 'IRR', key: 'irr', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'performance', fullTitle: 'IRR', unitKind: 'ratio',
        description: 'Money-weighted internal rate of return since the position was opened.' },
    ],
  },
]

export const closedPositionsHeaders = [
  {
    title: 'Type', key: 'type', align: 'start', sortable: false,
    groupId: 'identity', fullTitle: 'Type', unitKind: 'identity', identity: true, pinned: true,
    description: 'Asset type of the security.',
  },
  {
    title: 'Name', key: 'name', align: 'start', sortable: true,
    groupId: 'identity', fullTitle: 'Security', unitKind: 'identity', identity: true, pinned: true,
    description: 'Security name; links to the security detail page.',
  },
  {
    title: 'Currency', key: 'currency', align: 'end', sortable: true,
    groupId: 'identity', fullTitle: 'Currency', unitKind: 'identity',
    description: 'Trading currency of the security.',
  },
  {
    title: 'Entry',
    key: 'entry',
    align: 'end',
    sortable: false,
    children: [
      {
        title: 'Date', key: 'investment_date', align: 'end', sortable: true,
        groupId: 'entry', fullTitle: 'Entry date', unitKind: 'date',
        description: 'Date the position was opened.',
      },
      {
        title: 'Value', key: 'entry_value', align: 'end', sortable: true,
        groupId: 'entry', fullTitle: 'Entry value', unitKind: 'reporting-money',
        description: 'Value of the initial investment in your reporting currency ({currency}).',
      },
    ],
  },
  {
    title: 'Exit',
    key: 'exit',
    align: 'end',
    sortable: false,
    children: [
      {
        title: 'Date', key: 'exit_date', align: 'end', sortable: true,
        groupId: 'exit', fullTitle: 'Exit date', unitKind: 'date',
        description: 'Date the position was closed.',
      },
      {
        title: 'Value', key: 'exit_value', align: 'end', sortable: true,
        groupId: 'exit', fullTitle: 'Exit value', unitKind: 'reporting-money',
        description: 'Value received when the position was closed, in your reporting currency ({currency}).',
      },
    ],
  },
  {
    title: 'Realized gain/(loss)',
    key: 'realized',
    align: 'end',
    sortable: false,
    children: [
      {
        title: 'Realized G/L', key: 'realized_gl', align: 'end', sortable: true,
        groupId: 'performance', fullTitle: 'Realized G/L amount', unitKind: 'reporting-money',
        description: 'Realized gain or (loss) in your reporting currency ({currency}).',
      },
      { title: 'Realized G/L %', key: 'price_change_percentage', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'performance', fullTitle: 'Realized G/L %', unitKind: 'ratio',
        description: 'Realized gain or (loss) relative to entry value, in percent.' },
    ],
  },
  {
    title: 'Capital distribution',
    key: 'capital',
    align: 'end',
    sortable: false,
    children: [
      {
        title: 'Cap. Distr.', key: 'capital_distribution', align: 'end', sortable: true,
        groupId: 'performance', fullTitle: 'Capital distribution amount', unitKind: 'reporting-money',
        description: 'Capital distributions received, in your reporting currency ({currency}).',
      },
      { title: 'Cap. Distr. %', key: 'capital_distribution_percentage', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'performance', fullTitle: 'Capital distribution %', unitKind: 'ratio',
        description: 'Capital distributions relative to entry value, in percent.' },
    ],
  },
  {
    title: 'Commission',
    key: 'commission',
    align: 'end',
    sortable: false,
    children: [
      {
        title: 'Commission', key: 'commission', align: 'end', sortable: true,
        groupId: 'performance', fullTitle: 'Commission amount', unitKind: 'reporting-money',
        description: 'Commissions paid, shown as negative amounts, in your reporting currency ({currency}).',
      },
      { title: 'Commission %', key: 'commission_percentage', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'performance', fullTitle: 'Commission %', unitKind: 'ratio',
        description: 'Commissions relative to entry value, in percent.' },
    ],
  },
  {
    title: 'Total return',
    key: 'total',
    align: 'end',
    sortable: false,
    children: [
      {
        title: 'Total Return', key: 'total_return_amount', align: 'end', sortable: true,
        groupId: 'performance', fullTitle: 'Total return amount', unitKind: 'reporting-money',
        description: 'Total return including capital distributions and after commissions, in your reporting currency ({currency}).',
      },
      { title: 'Total Return %', key: 'total_return_percentage', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'performance', fullTitle: 'Total return %', unitKind: 'ratio',
        description: 'Total return incl. capital distributions and after commissions, relative to entry value.' },
      { title: 'IRR', key: 'irr', align: 'end', sortable: true, class: 'font-italic',
        groupId: 'performance', fullTitle: 'IRR', unitKind: 'ratio',
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
