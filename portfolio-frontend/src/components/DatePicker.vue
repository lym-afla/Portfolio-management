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
        <v-date-picker v-model="date" @update:model-value="selectDate"></v-date-picker>
      </v-dialog>
    </v-container>
  </template>
  
  <script>
  import { ref, watch } from 'vue'
  import { format, parse, isValid } from 'date-fns'
  
  export default {
    props: {
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
    },
    emits: ['update:modelValue'],
    setup(props, { emit }) {
      const date = ref(props.modelValue ? new Date(props.modelValue) : null)
      const showDatePicker = ref(false)
      const inputDate = ref(props.modelValue ? format(new Date(props.modelValue), 'dd/MM/yyyy') : '')

      const updateDate = (event) => {
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

      const formatDate = () => {
        if (date.value && isValid(date.value)) {
          inputDate.value = format(date.value, 'dd/MM/yyyy')
        }
      }

      const selectDate = (newDate) => {
        date.value = new Date(newDate)
        inputDate.value = format(date.value, 'dd/MM/yyyy')
        emit('update:modelValue', format(date.value, 'yyyy-MM-dd'))
        showDatePicker.value = false
      }

      watch(() => props.modelValue, (newValue) => {
        if (newValue) {
          date.value = new Date(newValue)
          inputDate.value = format(date.value, 'dd/MM/yyyy')
        } else {
          date.value = null
          inputDate.value = ''
        }
      })

      return {
        date,
        showDatePicker,
        inputDate,
        updateDate,
        formatDate,
        selectDate,
      }
    },
  }
  </script>