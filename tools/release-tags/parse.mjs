import { parseTorrentTitle } from './vendor/dist/index.js';

const languages = {rus:'ru',ru:'ru',рус:'ru',eng:'en',en:'en',англ:'en',ukr:'uk',uk:'uk',укр:'uk',ger:'de',deu:'de',de:'de',fre:'fr',fra:'fr',fr:'fr',jpn:'ja',ja:'ja',spa:'es',es:'es',ita:'it',it:'it',kor:'ko',ko:'ko',chi:'zh',zho:'zh',zh:'zh'};
const languageList = text => [...new Set((text.toLowerCase().match(/[а-яёa-z]+/gu) || []).map(s=>languages[s]).filter(Boolean))];
export function parseTitle(title) {
    const p = parseTorrentTitle(title);
    const tags = {};
    const put = (key,value) => { if (value && (!Array.isArray(value) || value.length)) tags[key]=value; };
    const dual = /^\s*([^/[\]()]{1,180}?)\s+\/\s+([^/[\]()]{1,200}?)(?=\s*[[(]|$)/u.exec(title);
    if (dual) { put('localTitle',dual[1].trim()); put('originalTitle',dual[2].trim()); }
    put('year', p.year);
    put('resolution', p.resolution);
    put('source', p.quality);
    put('codec', p.codec);
    put('bitDepth',p.bitDepth);
    put('hdr',p.hdr);
    put('audio',p.audio);
    put('channels',p.channels);
    put('editions',p.editions);
    put('seasons',p.seasons);
    put('episodes',p.episodes);
    put('dubbed',p.dubbed);
    put('subbed',p.subbed);
    const dub = /\bDub\s*\(([^()]{1,80})\)/iu.exec(title);
    if (dub) put('dubLabel',dub[1].trim());
    const subs = [...title.matchAll(/\bSubs?\s*\(([^()]{1,100})\)/giu)];
    put('subtitleLanguages',[...new Set(subs.flatMap(m=>languageList(m[1])))]);
    const orig = /\bOriginal\s*(?:\(([^()]{1,40})\)|([a-zа-яё]{2,5})(?![a-zа-яё]))/iu.exec(title);
    if (orig) put('originalAudioLanguages', languageList(orig[1] || orig[2]));
    return tags;
}
