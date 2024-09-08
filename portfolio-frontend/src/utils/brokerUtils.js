export const formatBrokerChoices = (choices) => {
  if (!Array.isArray(choices)) {
    console.error('Received invalid choices format:', choices)
    return []
  }

  return choices.flatMap(choice => {
    if (choice[0] === '__SEPARATOR__') {
      return { type: 'divider' }
    } else if (Array.isArray(choice[1])) {
      return [
        { type: 'header', title: choice[0] },
        ...choice[1].map(subChoice => ({
          type: 'option',
          title: subChoice[1],
          value: subChoice[0]
        }))
      ]
    } else {
      return {
        type: 'option',
        title: choice[1],
        value: choice[0]
      }
    }
  })
}