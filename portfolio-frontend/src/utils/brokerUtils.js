export const formatBrokerChoices = (choices) => {
  return choices.flatMap(group => {
    if (group[0] === '__SEPARATOR__') {
      return { type: 'divider' }
    }
    if (Array.isArray(group[1])) {
      return [
        { title: group[0], type: 'header' },
        ...group[1].map(choice => ({
          title: choice[1],
          value: choice[0],
          type: 'option'
        }))
      ]
    }
    return {
      title: group[1],
      value: group[0],
      type: 'option'
    }
  })
}