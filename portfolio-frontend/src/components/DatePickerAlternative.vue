<template>
    <v-menu
      v-model="menu"
      :close-on-content-click="false"
      transition="scale-transition"
      offset-y
      min-width="auto"
    >
      <template v-slot:activator="{ on, attrs }">
        <v-text-field
          v-model="dateFormatted"
          label="Date"
          :error-messages="errorMessage"
          @input="formatInput"
          @blur="validateDate"
          @keypress="filterInput"
          placeholder="MM/DD/YYYY"
        >
          <template v-slot:append>
            <v-icon v-bind="attrs" v-on="on">mdi-calendar</v-icon>
          </template>
        </v-text-field>
      </template>
      <v-date-picker
        v-model="date"
        @input="menu = false"
      ></v-date-picker>
    </v-menu>
  </template>
  
  <script>
  import { ref, watch } from 'vue'
  
  export default {
    setup() {
      const date = ref(null)
      const dateFormatted = ref('')
      const menu = ref(false)
      const errorMessage = ref('')
  
      const formatDate = (date) => {
        if (!date) return ''
        const [year, month, day] = date.split('-')
        return `${month}/${day}/${year}`
      }
  
      const parseDate = (dateString) => {
        const [month, day, year] = dateString.split('/')
        return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`
      }
  
      const filterInput = (event) => {
        const charCode = (event.which) ? event.which : event.keyCode
        if (charCode > 31 && (charCode < 48 || charCode > 57)) {
          event.preventDefault()
        }
      }
  
      const formatInput = (value) => {
        // Remove any non-digit characters
        let numericValue = value.replace(/\D/g, '')
        
        // Limit to 8 digits
        numericValue = numericValue.slice(0, 8)
        
        // Format as MM/DD/YYYY
        if (numericValue.length > 4) {
          dateFormatted.value = `${numericValue.slice(0, 2)}/${numericValue.slice(2, 4)}/${numericValue.slice(4)}`
        } else if (numericValue.length > 2) {
          dateFormatted.value = `${numericValue.slice(0, 2)}/${numericValue.slice(2)}`
        } else {
          dateFormatted.value = numericValue
        }
  
        errorMessage.value = ''
      }
  
      const validateDate = () => {
        if (!dateFormatted.value) {
          date.value = null
          return
        }
  
        const dateRegex = /^(0[1-9]|1[0-2])\/(0[1-9]|[12]\d|3[01])\/\d{4}$/
        if (!dateRegex.test(dateFormatted.value)) {
          errorMessage.value = 'Invalid date format. Use MM/DD/YYYY'
          return
        }
  
        const parsedDate = parseDate(dateFormatted.value)
        if (isNaN(Date.parse(parsedDate))) {
          errorMessage.value = 'Invalid date'
          return
        }
  
        date.value = parsedDate
        errorMessage.value = ''
      }
  
      watch(date, (newDate) => {
        dateFormatted.value = formatDate(newDate)
      })
  
      return {
        date,
        dateFormatted,
        menu,
        errorMessage,
        formatInput,
        validateDate,
        filterInput,
      }
    },
  }
  </script>