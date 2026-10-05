// D6 browser case: minimal RFC6455 server-side frame codec plus the
// synthetic /ws/transactions/ conversation driver. It reproduces the real
// backend producer envelopes (docs/design/frontend-import-workflow.md) so
// the rendered flow runs against genuine shapes, records every client
// command verbatim for exact-payload assertions, and supports delayed
// delivery of stale events across close/reopen.
import { createHash } from 'node:crypto'

export function createImportsWs() {
  const state = {
    commands: [], // every client command, exact parsed objects
    conversations: [], // summary of started conversations
    rejectUpgrades: false,
    lateQueue: [], // messages held until flushLate()
    sockets: new Set(),
    scenario: 'file',
    upgrades: 0,
  }

  const encodeText = (text) => {
    const payload = Buffer.from(text, 'utf8')
    const length = payload.length
    let header
    if (length < 126) {
      header = Buffer.from([0x81, length])
    } else if (length < 65536) {
      header = Buffer.alloc(4)
      header[0] = 0x81
      header[1] = 126
      header.writeUInt16BE(length, 2)
    } else {
      header = Buffer.alloc(10)
      header[0] = 0x81
      header[1] = 127
      header.writeBigUInt64BE(BigInt(length), 2)
    }
    return Buffer.concat([header, payload])
  }

  // Incremental frame parser: client frames are masked per RFC6455.
  const createParser = (onText) => {
    let buffer = Buffer.alloc(0)
    return (chunk) => {
      buffer = Buffer.concat([buffer, chunk])
      for (;;) {
        if (buffer.length < 2) return
        const first = buffer[0]
        const opcode = first & 0x0f
        const masked = (buffer[1] & 0x80) !== 0
        let length = buffer[1] & 0x7f
        let offset = 2
        if (length === 126) {
          if (buffer.length < 4) return
          length = buffer.readUInt16BE(2)
          offset = 4
        } else if (length === 127) {
          if (buffer.length < 10) return
          length = Number(buffer.readBigUInt64BE(2))
          offset = 10
        }
        const maskKey = masked ? buffer.subarray(offset, offset + 4) : null
        if (masked) offset += 4
        if (buffer.length < offset + length) return
        const payload = Buffer.from(buffer.subarray(offset, offset + length))
        if (maskKey) {
          for (let i = 0; i < payload.length; i += 1) {
            payload[i] ^= maskKey[i % 4]
          }
        }
        buffer = buffer.subarray(offset + length)
        if (opcode === 0x1) onText(payload.toString('utf8'))
        // Opcode 0x8 (close) is handled by the socket close event; pings are
        // ignored (the browser does not ping within a test's lifetime).
      }
    }
  }

  const sendTo = (socket, message) => {
    if (!socket || socket.destroyed) return false
    socket.write(encodeText(JSON.stringify(message)))
    return true
  }

  const sendToAll = (message) => {
    for (const socket of state.sockets) sendTo(socket, message)
  }

  const importUpdate = (data) => sendToAll({ type: 'import_update', data })

  const completePayload = (overrides = {}) => ({
    totalTransactions: 3,
    importedTransactions: 3,
    skippedTransactions: 0,
    duplicateTransactions: 0,
    importErrors: 0,
    warnings: [],
    ...overrides,
  })

  const transactionDisplay = {
    date: '2026-09-01',
    type: 'Buy',
    security: { id: 3, name: 'ACME Corp' },
    quantity: '10',
    price: '115.50',
    total: 1155.0,
    commission: '1.15',
  }

  const handleCommand = (raw) => {
    let command
    try {
      command = JSON.parse(raw)
    } catch {
      return
    }
    state.commands.push(command)
    switch (command.type) {
      case 'start_file_import': {
        state.conversations.push({ type: 'file', at: Date.now() })
        importUpdate({
          status: 'total_count',
          total: 3,
          message: 'Found 3 transactions',
        })
        importUpdate({
          status: 'progress',
          current: 1,
          message: 'Processing transaction 1 of 3',
          progress: 33,
        })
        importUpdate({
          status: 'transaction_confirmation',
          data: transactionDisplay,
        })
        break
      }
      case 'transaction_confirmed': {
        importUpdate({
          status: 'transaction_saved',
          current: 1,
          total: 3,
          message: 'Saved transaction 1 of 3',
          transaction: { count: 1 },
        })
        sendToAll({
          type: 'import_complete',
          data: completePayload({
            warnings: [
              {
                endpoint: 'spot_fills',
                error: 'OKX HTTP 500: synthetic endpoint failure',
              },
            ],
          }),
          message: 'Import process completed',
        })
        break
      }
      case 'start_api_import': {
        state.conversations.push({ type: 'api', at: Date.now() })
        sendToAll({
          type: 'account_matching_required',
          data: {
            broker_id: command.data?.broker_id ?? 11,
            broker_name: 'Tinkoff',
            matched_pairs: {
              '222444555': {
                tinkoff_account: {
                  id: '222444555',
                  name: 'T-Invest Brokerage',
                  type: 'BROKERAGE',
                },
                db_account: { id: 7, name: 'Tinkoff Main', broker: 2 },
              },
            },
            unmatched_tinkoff: [
              { id: '333555777', name: 'T-Invest Savings', type: 'SAVINGS' },
            ],
            unmatched_db: [{ id: 9, name: 'Secondary account' }],
            message: 'Please confirm account matches and match remaining accounts',
          },
        })
        break
      }
      case 'accounts_matched':
      case 'use_existing_matches': {
        importUpdate({
          status: 'progress',
          current: 0,
          message: 'Starting import for 1 account pairs',
          progress: 0,
        })
        importUpdate({
          status: 'security_mapping',
          mapping_data: {
            security_description: 'ACME Corp',
            isin: 'US0000000001',
            symbol: 'ACME',
            best_match: { match_id: 31, match_name: 'ACME Corp.', match_score: 0.87 },
          },
          transaction_data: transactionDisplay,
        })
        break
      }
      case 'security_mapped': {
        importUpdate({
          status: 'transaction_saved',
          current: 1,
          total: 1,
          message: 'Saved transaction 1 of 1',
          transaction: { count: 1 },
        })
        sendToAll({
          type: 'import_complete',
          data: completePayload({ totalTransactions: 1, importedTransactions: 1 }),
          message: 'Import process completed',
        })
        break
      }
      case 'stop_import': {
        // Hold the acknowledgment so the rendered stopping state (disabled
        // stop control, no outcome yet) is observable and capturable; the
        // flow answers it explicitly.
        state.pendingStop = true
        break
      }
      default:
        break
    }
  }

  const attach = (request, socket) => {
    const key = request.headers['sec-websocket-key']
    if (!key) throw new Error('Missing Sec-WebSocket-Key')
    state.upgrades += 1
    const accept = createHash('sha1')
      .update(`${key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
      .digest('base64')
    socket.write(
      'HTTP/1.1 101 Switching Protocols\r\n' +
        'Upgrade: websocket\r\n' +
        'Connection: Upgrade\r\n' +
        `Sec-WebSocket-Accept: ${accept}\r\n\r\n`,
    )
    const parse = createParser(handleCommand)
    socket.on('data', parse)
    socket.once('close', () => state.sockets.delete(socket))
    socket.on('error', () => state.sockets.delete(socket))
    state.sockets.add(socket)
  }

  return {
    state,
    attach,
    sendToAll,
    // Failed-connect scenario: sever every live socket and make the next
    // upgrade attempt fail.
    sever: () => {
      for (const socket of state.sockets) socket.destroy()
      state.sockets.clear()
      state.rejectUpgrades = true
    },
    queueLate: (message) => {
      state.lateQueue.push(message)
    },
    answerStop: () => {
      if (!state.pendingStop) return false
      state.pendingStop = false
      sendToAll({
        type: 'import_stopped',
        data: {
          message: 'Import process was stopped by user',
          stats: {
            totalTransactions: 1,
            importedTransactions: 1,
            skippedTransactions: 0,
            duplicateTransactions: 0,
            importErrors: 0,
          },
        },
      })
      return true
    },
    flushLate: () => {
      const messages = state.lateQueue.splice(0)
      for (const message of messages) sendToAll(message)
      return messages.length
    },
  }
}
