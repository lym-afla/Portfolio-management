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
          ></v-select>
          <v-row>
            <v-col cols="6">
              <v-text-field
                v-model="dateFrom"
                label="From"
                type="date"
              ></v-text-field>
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model="dateTo"
                label="To"
                type="date"
              ></v-text-field>
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="applyDateRange">Apply</v-btn>
        </v-card-actions>
      </v-card>
    </v-menu>
  </template>
  
  <script>
  import { ref, computed } from 'vue'
  import { useStore } from 'vuex'
  import { format, parseISO, startOfYear, subMonths, subYears } from 'date-fns'
  
  export default {
    name: 'DateRangeSelector',
    props: {
      modelValue: {
        type: Object,
        default: () => ({ from: null, to: null })
      }
    },
    emits: ['update:modelValue'],
    setup(props, { emit }) {
      const store = useStore()
      const menu = ref(false)
      const selectedRange = ref('ytd')
      const dateFrom = ref(props.modelValue.from)
      const dateTo = ref(props.modelValue.to)
  
      const effectiveCurrentDate = computed(() => store.state.effectiveCurrentDate)
  
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
          { title: 'All', value: 'all_time' },
        ]
      })
  
      const displayDateRange = computed(() => {
        if (dateFrom.value && dateTo.value) {
          return `${format(parseISO(dateFrom.value), 'dd MMM yyyy')} - ${format(parseISO(dateTo.value), 'dd MMM yyyy')}`
        }
        return 'Select Date Range'
      })
  
      const handlePredefinedRange = (value) => {
        const effectiveDate = parseISO(effectiveCurrentDate.value)
        let fromDate
  
        switch (value) {
          case 'ytd':
            fromDate = startOfYear(effectiveDate)
            break
          case 'last1m':
            fromDate = subMonths(effectiveDate, 1)
            break
          case 'last3m':
            fromDate = subMonths(effectiveDate, 3)
            break
          case 'last6m':
            fromDate = subMonths(effectiveDate, 6)
            break
          case 'last12m':
            fromDate = subMonths(effectiveDate, 12)
            break
          case 'last3y':
            fromDate = subYears(effectiveDate, 3)
            break
          case 'last5y':
            fromDate = subYears(effectiveDate, 5)
            break
          case 'all_time':
            fromDate = new Date('1900-01-01')
            break
        }
  
        dateFrom.value = format(fromDate, 'yyyy-MM-dd')
        dateTo.value = format(effectiveDate, 'yyyy-MM-dd')
      }
  
      const applyDateRange = () => {
        emit('update:modelValue', { from: dateFrom.value, to: dateTo.value })
        menu.value = false
      }
  
      return {
        menu,
        selectedRange,
        dateFrom,
        dateTo,
        dateRangeOptions,
        displayDateRange,
        handlePredefinedRange,
        applyDateRange
      }
    }
  }
  </script>