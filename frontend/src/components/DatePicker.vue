<template>
  <v-container>
    <v-row>
      <v-col cols="12" sm="6" md="4">
        <v-text-field
          v-model="inputDate"
          :label="label"
          placeholder="DD/MM/YYYY"
          @input="updateDate"
          @blur="formatDate"
          hide-details="auto"
          :error-messages="errorMessage"
        >
          <template v-slot:append>
            <v-icon @click="showDatePicker = true">mdi-calendar</v-icon>
          </template>
        </v-text-field>
      </v-col>
    </v-row>

    <v-dialog v-model="showDatePicker" max-width="290px">
      <v-date-picker v-model="date" @update:model-value="selectDate" />
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, watch } from 'vue'
import { format, parse, isValid } from 'date-fns'

const props = defineProps({
  modelValue: {
    type: String,
    default: '',
  },
  label: {
    type: String,
    default: 'Date',
  },
  errorMessage: {
    type: String,
    default: '',
  },
})
const emit = defineEmits(['update:modelValue'])

const date = ref(props.modelValue ? new Date(props.modelValue) : null)
const showDatePicker = ref(false)
const inputDate = ref(
  props.modelValue ? format(new Date(props.modelValue), 'dd/MM/yyyy') : ''
)

function updateDate(event) {
  const value = event.target.value
  inputDate.value = value
  if (value && value.length === 10) {
    const parsedDate = parse(value, 'dd/MM/yyyy', new Date())
    if (isValid(parsedDate)) {
      date.value = parsedDate
      emit('update:modelValue', format(parsedDate, 'yyyy-MM-dd'))
    }
  } else {
    emit('update:modelValue', '')
  }
}

function formatDate() {
  if (date.value && isValid(date.value)) {
    inputDate.value = format(date.value, 'dd/MM/yyyy')
  }
}

function selectDate(newDate) {
  date.value = new Date(newDate)
  inputDate.value = format(date.value, 'dd/MM/yyyy')
  emit('update:modelValue', format(date.value, 'yyyy-MM-dd'))
  showDatePicker.value = false
}

watch(
  () => props.modelValue,
  (newValue) => {
    if (newValue) {
      date.value = new Date(newValue)
      inputDate.value = format(date.value, 'dd/MM/yyyy')
    } else {
      date.value = null
      inputDate.value = ''
    }
  }
)
</script>
