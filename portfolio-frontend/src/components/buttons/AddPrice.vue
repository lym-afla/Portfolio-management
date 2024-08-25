<template>
    <v-btn color="primary" @click="addPriceEntry">
      <v-icon left>mdi-plus</v-icon>
      Add Price Entry
    </v-btn>
  </template>
  
  <script>
  export default {
    name: 'AddPriceEntryButton',
    setup() {
      const addPriceEntry = () => {
        // TODO: Implement add price entry logic
        console.log('Adding price entry');
      };
  
      return { addPriceEntry };
    }
  }
  </script>