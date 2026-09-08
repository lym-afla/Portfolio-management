function toError(error) {
  return error instanceof Error ? error : new Error(String(error))
}

function resourceError(resource, error) {
  const cause = toError(error)
  return new Error(`${resource}: ${cause.message}`, { cause })
}

export async function cleanupBrowserHarness({
  sessions,
  closeSession,
  closeAppServer,
  closeFixtureServer,
  recordError,
}) {
  const errors = []

  async function attempt(resource, closeResource) {
    try {
      await closeResource()
    } catch (error) {
      const failure = resourceError(resource, error)
      errors.push(failure)
      try {
        await recordError?.({ context: resource, error: failure.message })
      } catch (recordFailure) {
        errors.push(resourceError(`${resource} error log`, recordFailure))
      }
    }
  }

  for (const [session, initScript] of sessions) {
    await attempt(`${session} close`, () => closeSession(session, initScript))
  }
  if (closeAppServer) {
    await attempt('app server close', closeAppServer)
  }
  await attempt('fixture server close', closeFixtureServer)

  if (errors.length > 0) {
    throw new AggregateError(
      errors,
      `Browser harness cleanup failed (${errors.length})`
    )
  }
}

export async function runBrowserHarnessLifecycle({ run, cleanup }) {
  let runFailure
  try {
    await run()
  } catch (error) {
    runFailure = toError(error)
  }

  let cleanupFailure
  try {
    await cleanup()
  } catch (error) {
    cleanupFailure = toError(error)
  }

  if (runFailure && cleanupFailure) {
    throw new AggregateError(
      [runFailure, cleanupFailure],
      'Browser smoke run and cleanup both failed',
      { cause: runFailure }
    )
  }
  if (runFailure) {
    throw runFailure
  }
  if (cleanupFailure) {
    throw cleanupFailure
  }
}
