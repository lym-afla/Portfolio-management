import logger from '@/utils/logger'

export const formatAccountChoices = (choices) => {
  if (!Array.isArray(choices)) {
    logger.error('Unknown', 'Received invalid choices format:', choices)
    return []
  }

  return choices.flatMap((choice) => {
    if (choice[0] === '__SEPARATOR__') {
      return { type: 'divider' }
    } else if (Array.isArray(choice[1])) {
      return [
        { type: 'header', title: choice[0] },
        ...choice[1].map((subChoice) => {
          if (subChoice[0] === 'All accounts') {
            return {
              type: 'option',
              title: 'All accounts',
              value: subChoice[1],
              raw: {
                type: 'option',
                title: 'All accounts',
              },
            }
          }

          return {
            type: 'option',
            title: subChoice[1].display_name,
            value: subChoice[1],
            raw: {
              type: 'option',
              title: subChoice[1].display_name,
            },
          }
        }),
      ]
    } else {
      return {
        type: 'option',
        title: choice[1].display_name,
        value: choice[1],
        raw: {
          type: 'option',
          title: choice[1].display_name,
        },
      }
    }
  })
}

// Single source for the committed-context account label: the matching choice
// title with the shared All accounts/Unavailable fallbacks. Used by the shell
// context strip and by pages that repeat committed provenance.
export const committedAccountLabel = (choices, selection) => {
  const options = formatAccountChoices(choices)
  const matched = options.find(
    (option) =>
      option.type === 'option' &&
      option.value?.type === selection.type &&
      option.value?.id === selection.id
  )
  return matched?.title ?? (selection.type === 'all' ? 'All accounts' : 'Unavailable')
}
