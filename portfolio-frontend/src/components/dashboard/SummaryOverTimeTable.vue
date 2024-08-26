<template>
  <v-card v-if="lines && years && currentYear">
    <v-card-title>Summary Over Time</v-card-title>
    <v-card-text>
      <v-table>
        <thead>
          <tr>
            <th></th>
            <th v-for="year in years" :key="year" class="text-center font-weight-bold">{{ year }}</th>
            <th class="text-center highlight font-weight-bold">{{ currentYear }}YTD</th>
            <th class="text-center highlight font-weight-bold">All-time</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="line in lines" :key="line.name" :class="{ 'font-weight-bold': line.name === 'BoP NAV' || line.name === 'EoP NAV', 'font-italic': line.name === 'TSR' }">
            <td>
              {{ line.name }}
            </td>
            <td v-for="year in years" :key="`${line.name}-${year}`" class="text-center">
              {{ formatValue(line.values[year]) }}
            </td>
            <td class="text-center highlight">{{ formatValue(line.values[currentYear + 'YTD']) }}</td>
            <td class="text-center font-weight-bold highlight">{{ formatValue(line.values['All-time']) }}</td>
          </tr>
        </tbody>
      </v-table>
    </v-card-text>
  </v-card>
</template>

<script>
export default {
  name: 'SummaryOverTimeTable',
  props: {
    lines: {
      type: Array,
      required: true
    },
    years: {
      type: Array,
      required: true
    },
    currentYear: {
      type: String,
      required: true
    }
  },
  methods: {
    formatValue(value) {
      if (typeof value === 'number') {
        return value.toFixed(2)
      }
      return value
    }
  }
}
</script>

<style scoped>
.highlight {
  background-color: rgba(0, 0, 0, 0.05);
}
</style>