export const formatAccountChoices = (choices) => {
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
        ...choice[1].map(subChoice => {
          if (subChoice[0] === 'All accounts') {
            return {
              type: 'option',
              title: 'All accounts',
              value: subChoice[1],
              raw: {
                type: 'option',
                title: 'All accounts'
              }
            }
          }
          
          return {
            type: 'option',
            title: subChoice[1].display_name,
            value: subChoice[1],
            raw: {
              type: 'option',
              title: subChoice[1].display_name
            }
          }
        })
      ]
    } else {
      return {
        type: 'option',
        title: choice[1].display_name,
        value: choice[1],
        raw: {
          type: 'option',
          title: choice[1].display_name
        }
      }
    }
  })
}