<template>
    <v-dialog v-model="dialog" persistent max-width="500px">
      <v-card>
        <v-card-title>Map Security</v-card-title>
        <v-card-text>
          <p>Unrecognized security: {{ security }}</p>
          <p v-if="bestMatch">Best match: {{ bestMatch[0] }} (Score: {{ bestMatch[1] }})</p>
          <v-select
            v-model="selectedSecurity"
            :items="securityOptions"
            label="Select Security"
            item-text="name"
            item-value="id"
          ></v-select>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="mapSecurity">Map</v-btn>
          <v-btn color="error" @click="skipSecurity">Skip</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </template>
  
  <script>
  import { ref, watch, computed } from 'vue'
  import { getSecurities } from '@/services/api'
  
  export default {
    props: {
      modelValue: Boolean,
      security: String,
      bestMatch: Array,
      brokerId: Number
    },
    emits: ['update:modelValue', 'security-mapped'],
    setup(props, { emit }) {
      const dialog = ref(props.modelValue)
      const selectedSecurity = ref(null)
      const securityOptions = computed(() => {
        const securities = getSecurities([], props.brokerId)
        return securities.map(security => ({
          id: security.id,
          name: security.name
        }))
      })
  
      watch(() => props.modelValue, (newValue) => {
        dialog.value = newValue
      })
  
      watch(dialog, (newValue) => {
        emit('update:modelValue', newValue)
      })
  
      const mapSecurity = () => {
        emit('security-mapped', selectedSecurity.value)
      }
  
      const skipSecurity = () => {
        emit('security-mapped', null)
      }
  
      return {
        dialog,
        selectedSecurity,
        securityOptions,
        mapSecurity,
        skipSecurity,
      }
    }
  }
  </script>