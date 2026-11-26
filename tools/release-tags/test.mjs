import assert from 'node:assert/strict';
import {parseTitle} from './parse.mjs';
const venom='Веном 2 / Venom: Let There Be Carnage (Энди Серкис / Andy Serkis) [2021, США, Фантастика, боевик, триллер, WEB-DLRip] Dub (iTunes) + Sub (Rus, Eng) + Original Eng';
assert.deepEqual(parseTitle(venom),{
    localTitle:'Веном 2',originalTitle:'Venom: Let There Be Carnage',year:'2021',source:'WEB-DLRip',
    dubbed:true,subbed:true,dubLabel:'iTunes',subtitleLanguages:['ru','en'],originalAudioLanguages:['en']
});
assert.equal(parseTitle('Название.2x2.WEB-DL.mkv').episodes,undefined);
assert.deepEqual(parseTitle('Show.2x03.1080p.mkv').episodes,[3]);
assert.deepEqual(parseTitle('Сериал (второй сезон) серии 1-4, 6-10').seasons,[2]);
assert.deepEqual(parseTitle('Сериал (второй сезон) серии 1-4, 6-10').episodes,[1,2,3,4,6,7,8,9,10]);
assert.equal(parseTitle('Film.1080p.WEB-DL.10bit.mkv').hdr,undefined);
assert.equal(parseTitle('Release title').codec,undefined);
console.log('release-title fixtures OK');
