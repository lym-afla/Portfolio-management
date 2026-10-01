import type { getDashboardSummary } from '@/services/api'
import type { MetricDisplay } from '@/components/workspace/types'

type DashboardSummaryData = Awaited<ReturnType<typeof getDashboardSummary>>

// Display-only mapping of the validated direct summary dictionary. The five
// fields arrive already formatted by the backend; this adapter assigns each
// one an explicit id, label and horizon without parsing or recalculating.
export function summaryMetrics(summary: DashboardSummaryData): readonly MetricDisplay[] {
  return [
    { id: 'nav', label: 'Total NAV', value: summary['Current NAV'] },
    { id: 'invested', label: 'Invested', value: summary.Invested },
    { id: 'cash-out', label: 'Cash out', value: summary['Cash-out'] },
    {
      id: 'total-return',
      label: 'Total return',
      value: summary.total_return,
      explanation: 'Since inception',
    },
    { id: 'irr', label: 'IRR since inception', value: summary.irr },
  ]
}
