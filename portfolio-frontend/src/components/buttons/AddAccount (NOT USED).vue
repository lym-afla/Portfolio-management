<template>
  <v-btn color="primary" @click="addAccount">
    <v-icon left>mdi-plus</v-icon>
    Add Account
  </v-btn>
</template>

<script>
export default {
  name: 'AddAccountButton',
  emits: ['add-account'],
  setup(props, { emit }) {
    const addAccount = () => {
      emit('add-account')
    }

    return { addAccount }
  }
}
</script>