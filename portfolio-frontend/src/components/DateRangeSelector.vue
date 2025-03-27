<template>
  <v-menu v-model="menu" :close-on-content-click="false" max-width="290">
    <template v-slot:activator="{ props }">
      <v-btn v-bind="props" prepend-icon="mdi-calendar" variant="outlined">
        {{ displayDateRange }}
      </v-btn>
    </template>
    <v-card>
      <v-card-text>
        <v-select
          v-model="selectedRange"
          :items="dateRangeOptions"
          label="Date Range"
          @update:model-value="handlePredefinedRange"
        />
        <v-row>
          <v-col cols="6">
            <v-text-field
              v-model="dateFrom"
              label="From"
              type="date"
              @update:model-value="handleManualDateChange"
            />
          </v-col>
          <v-col cols="6">
            <v-text-field
              v-model="dateTo"
              label="To"
              type="date"
              @update:model-value="handleManualDateChange"
            />
          </v-col>
        </v-row>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn color="primary" @click="applyDateRange">Apply</v-btn>
      </v-card-actions>
    </v-card>
  </v-menu>
</template>

<script>
import { ref, computed, watch, onMounted } from 'vue'
import { useStore } from 'vuex'
import { format, parseISO } from 'date-fns'
import { calculateDateRange } from '@/utils/dateRangeUtils'

export default {
  name: 'DateRangeSelector',
  props: {
    modelValue: {
      type: Object,
      default: () => ({ dateRange: 'ytd', dateFrom: null, dateTo: null }),
    },
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    const store = useStore()
    const menu = ref(false)
    const selectedRange = ref(props.modelValue.dateRange)
    const dateFrom = ref(props.modelValue.dateFrom)
    const dateTo = ref(props.modelValue.dateTo)

    const effectiveCurrentDate = computed(
      () => store.state.effectiveCurrentDate
    )

    const dateRangeOptions = computed(() => {
      const currentYear = new Date(effectiveCurrentDate.value).getFullYear()
      return [
        { title: `${currentYear}YTD`, value: 'ytd' },
        { title: 'Last 1 Month', value: 'last1m' },
        { title: 'Last 3 Months', value: 'last3m' },
        { title: 'Last 6 Months', value: 'last6m' },
        { title: 'Last 12 Months', value: 'last12m' },
        { title: 'Last 3 Years', value: 'last3y' },
        { title: 'Last 5 Years', value: 'last5y' },
        { title: 'All-time', value: 'all_time' },
        { title: 'Custom', value: 'custom' },
      ]
    })

    const displayDateRange = computed(() => {
      if (!dateFrom.value && !dateTo.value) {
        return 'Select Date Range'
      }

      const formatDate = (date) =>
        date ? format(parseISO(date), 'dd MMM yyyy') : 'Start'
      const fromStr = formatDate(dateFrom.value)
      const toStr = formatDate(dateTo.value)

      return `${fromStr} ➔ ${toStr}`
    })

    const handlePredefinedRange = (value) => {
      selectedRange.value = value
      if (value !== 'custom') {
        updateDateRange()
      }
    }

    const handleManualDateChange = () => {
      selectedRange.value = 'custom'
    }

    const updateDateRange = () => {
      if (effectiveCurrentDate.value) {
        const calculatedDateRange = calculateDateRange(
          selectedRange.value,
          effectiveCurrentDate.value
        )
        dateFrom.value = calculatedDateRange.from
        dateTo.value = calculatedDateRange.to
      }
    }

    const applyDateRange = () => {
      emit('update:modelValue', {
        dateRange: selectedRange.value,
        dateFrom: dateFrom.value,
        dateTo: dateTo.value,
      })
      menu.value = false
    }

    // Watch for changes in the modelValue prop
    watch(
      () => props.modelValue,
      (newValue) => {
        selectedRange.value = newValue.dateRange
        dateFrom.value = newValue.dateFrom
        dateTo.value = newValue.dateTo
      },
      { deep: true }
    )

    // Watch for changes in effectiveCurrentDate
    watch(effectiveCurrentDate, () => {
      if (selectedRange.value !== 'custom') {
        updateDateRange()
      }
    })

    // Initialize the component
    onMounted(() => {
      if (!dateFrom.value || !dateTo.value) {
        updateDateRange()
      }
    })

    return {
      menu,
      selectedRange,
      dateFrom,
      dateTo,
      dateRangeOptions,
      displayDateRange,
      handlePredefinedRange,
      handleManualDateChange,
      applyDateRange,
    }
  },
}
</script>
