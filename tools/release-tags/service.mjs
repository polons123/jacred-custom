import {DatabaseSync} from 'node:sqlite';
import {createServer} from 'node:http';
import {chmodSync, lstatSync, unlinkSync} from 'node:fs';
import {parseTitle} from './parse.mjs';

const [database, socket] = process.argv.slice(2);
const db = new DatabaseSync(database);
db.exec('PRAGMA busy_timeout=1200; PRAGMA journal_mode=WAL');
const lookup = db.prepare('SELECT data FROM tags WHERE title=?');
const store = db.prepare('INSERT OR IGNORE INTO tags(title,data) VALUES (?,?)');
function releaseTags(titles) {
    const result = [], missing = [];
    for (const title of titles) {
        const row = lookup.get(title);
        if (row) result.push(JSON.parse(row.data));
        else {
            const parsed = parseTitle(title);
            missing.push([title,JSON.stringify(parsed)]);
            result.push(parsed);
        }
    }
    if (missing.length) {
        db.exec('BEGIN IMMEDIATE');
        try {
            for (const [title,data] of missing) store.run(title,data);
            db.exec('COMMIT');
        } catch(error) {
            db.exec('ROLLBACK');
            throw error;
        }
    }
    return result;
}
const server = createServer(async (req,res) => {
    if(req.method!=='POST' || req.url!=='/titles') {res.writeHead(404).end();return;}
    try {
        const chunks=[]; let bytes=0;
        for await(const chunk of req) {
            bytes+=chunk.length;
            if(bytes>4*1024*1024) {res.writeHead(413).end();return;}
            chunks.push(chunk);
        }
        const titles=JSON.parse(Buffer.concat(chunks).toString('utf8'));
        if(!Array.isArray(titles) || titles.length>256 || titles.some(v=>typeof v!=='string' || v.length>32768)) {
            res.writeHead(400).end();return;
        }
        const data=releaseTags(titles);
        res.writeHead(200,{'Content-Type':'application/json'}).end(JSON.stringify(data));
    } catch(error) {
        console.error('release tags request failed',error.name,error.code || '');
        res.writeHead(503).end();
    }
});
if(lstatSync(socket,{throwIfNoEntry:false})?.isSocket()) unlinkSync(socket);
server.listen(socket,()=>chmodSync(socket,0o660));
