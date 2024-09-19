<template>
    <v-dialog v-model="dialog" persistent max-width="500px">
      <v-card>
        <v-card-title>Confirm Transaction</v-card-title>
        <v-card-text>
            <p>Transaction {{ index }} of {{ total }}</p>
            <v-list>
                <v-list-item v-for="(value, key) in transaction" :key="key">
                    <v-list-item-title>{{ key }}:</v-list-item-title>
                    <v-list-item-subtitle>{{ value }}</v-list-item-subtitle>
                </v-list-item>
            </v-list>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="confirm">Confirm</v-btn>
          <v-btn color="error" @click="skip">Skip</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </template>
  
  <script>
  import { ref, watch } from 'vue'
  
  export default {
    props: {
      modelValue: Boolean,
      transaction: Object,
      index: Number,
      total: Number,
    },
    emits: ['update:modelValue', 'confirm', 'skip'],
    setup(props, { emit }) {
      const dialog = ref(props.modelValue)
  
      watch(() => props.modelValue, (newValue) => {
        dialog.value = newValue
      })
  
      watch(dialog, (newValue) => {
        emit('update:modelValue', newValue)
      })
  
      const confirm = () => {
        emit('confirm')
      }
  
      const skip = () => {
        emit('skip')
      }
  
      return {
        dialog,
        confirm,
        skip,
      }
    }
}
</script>