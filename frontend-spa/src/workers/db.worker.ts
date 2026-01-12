import sqlite3InitModule from '@sqlite.org/sqlite-wasm';

const DB_NAME = 'llm_fantasy_data.db';
let db: any = null;

// Worker message handling
self.onmessage = async (e: MessageEvent) => {
  const { type, payload, id } = e.data;

  try {
    switch (type) {
      case 'INIT_DB':
        await initDB();
        self.postMessage({ type: 'INIT_SUCCESS', id });
        break;
      case 'EXEC_SQL':
        const result = await execSQL(payload.sql);
        self.postMessage({ type: 'EXEC_SUCCESS', id, payload: result });
        break;
      default:
        throw new Error(`Unknown message type: ${type}`);
    }
  } catch (error: any) {
    self.postMessage({ type: 'ERROR', id, error: error.message });
  }
};

async function initDB() {
  if (db) return;

  const log = (...args: any[]) => console.log('[DB Worker]', ...args);
  log('Initializing SQLite3...');

  try {
    const sqlite3 = await sqlite3InitModule({
      print: log,
      printErr: console.error,
    });

    // Check if OPFS is supported by checking if OpfsDb is available
    if (!sqlite3.oo1.OpfsDb) {
      throw new Error('OPFS is not available in this browser environment.');
    }

    log('Fetching database from assets...');
    const response = await fetch('/assets/llm_fantasy_data.db');
    const arrayBuffer = await response.arrayBuffer();

    // We need to write the file to OPFS before opening it with OpfsDb
    // The standard way in sqlite-wasm is using the installOpfsSAHPOOL or just direct file writing if supported.
    // However, sqlite3.oo1.OpfsDb.importDb is the utility for this.
    // Note: The types might not reflect this extension method, so we cast to any.

    const opfsDbUtil = sqlite3.oo1.OpfsDb as any;
    if (opfsDbUtil.importDb) {
        await opfsDbUtil.importDb(DB_NAME, arrayBuffer);
    } else {
        throw new Error("importDb not supported in this version of sqlite-wasm");
    }

    db = new sqlite3.oo1.OpfsDb(DB_NAME);

    log('Database loaded successfully into OPFS.');
  } catch (err) {
    console.error('Failed to initialize DB', err);
    throw err;
  }
}

async function execSQL(sql: string) {
  if (!db) throw new Error('Database not initialized');

  const results: any[] = [];
  db.exec({
    sql,
    rowMode: 'object',
    callback: (row: any) => {
      results.push(row);
    },
  });
  return results;
}
