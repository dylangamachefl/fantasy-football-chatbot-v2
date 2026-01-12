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
        self.postMessage({ type: 'EXEC_SQL_SUCCESS', id, payload: result });
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

    if (!sqlite3.oo1.OpfsDb) {
      throw new Error('OPFS is not available in this browser environment.');
    }

    const opfsDbUtil = sqlite3.oo1.OpfsDb as any;

    // Check if the database already exists in OPFS
    let dbExists = false;
    try {
      const opfsRoot = await navigator.storage.getDirectory();
      await opfsRoot.getFileHandle(DB_NAME);
      dbExists = true;
      log('Database found in OPFS.');
    } catch (e) {
      log('Database not found in OPFS, will fetch from assets.');
    }

    if (!dbExists) {
      log('Fetching database from assets...');
      const response = await fetch('/assets/llm_fantasy_data.db');
      const arrayBuffer = await response.arrayBuffer();

      if (opfsDbUtil.importDb) {
        await opfsDbUtil.importDb(DB_NAME, arrayBuffer);
        log('Database imported into OPFS.');
      } else {
        throw new Error("importDb not supported in this version of sqlite-wasm");
      }
    }

    db = new sqlite3.oo1.OpfsDb(DB_NAME);
    log('Database loaded successfully.');
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
