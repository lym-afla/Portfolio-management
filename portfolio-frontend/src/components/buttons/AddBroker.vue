<template>
  <v-btn color="primary" @click="addBroker">
    <v-icon left>mdi-plus</v-icon>
    Add Broker
  </v-btn>
</template>

<script>
export default {
  name: 'AddBrokerButton',
  emits: ['add-broker'],
  setup(props, { emit }) {
    const addBroker = () => {
      emit('add-broker')
    }

    return { addBroker }
  }
}
</script>