<template>
    <v-btn color="primary" @click="openDialog">
      <v-icon left>mdi-plus</v-icon>
      Add Price Entry
    </v-btn>
    <PriceFormDialog v-model="showDialog" @price-added="handlePriceAdded" />
</template>

<script>
import { ref } from 'vue'
import PriceFormDialog from '@/components/dialogs/PriceFormDialog.vue'

export default {
  name: 'AddPriceEntryButton',
  components: {
    PriceFormDialog,
  },
  setup() {
    const showDialog = ref(false)

    const openDialog = () => {
      showDialog.value = true
    }

    const handlePriceAdded = (newPrice) => {
      // Handle the newly added price (e.g., update the price list in the parent component)
      console.log('New price added:', newPrice)
    }

    return {
      showDialog,
      openDialog,
      handlePriceAdded,
    }
  }
}
</script>