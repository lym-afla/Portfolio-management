<template>
    <v-btn color="primary" @click="addSecurity">
      <v-icon left>mdi-plus</v-icon>
      Add Security
    </v-btn>
  </template>
  
  <script>
  export default {
    name: 'AddSecurityButton',
    setup() {
      const addSecurity = () => {
        // TODO: Implement add security logic
        console.log('Adding security');
      };
  
      return { addSecurity };
    }
  }
  </script>