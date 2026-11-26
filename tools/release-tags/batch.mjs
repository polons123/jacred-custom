import readline from 'node:readline';
import {parseTitle} from './parse.mjs';
for await (const line of readline.createInterface({input:process.stdin})) {
    const tags = JSON.parse(line).map(parseTitle);
    process.stdout.write(JSON.stringify(tags)+'\n');
}
