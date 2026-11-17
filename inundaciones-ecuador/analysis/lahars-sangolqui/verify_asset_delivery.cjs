const fs=require('fs'),vm=require('vm'),assert=require('assert'),zlib=require('zlib'),crypto=require('crypto');
const path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../dist/lahars.js'),'utf8');
const bytes=zlib.gzipSync(JSON.stringify({verified:true}));
const hash=crypto.createHash('sha256').update(bytes).digest('hex');
let requested;
const ctx={location:{hostname:'localhost'},crypto:crypto.webcrypto,Blob,Response,DecompressionStream,TextDecoder,
 fetch:async url=>{requested=url;return new Response(bytes);}};
vm.createContext(ctx);
vm.runInContext("const root='data/sangolqui-lahars/';"+source.slice(source.indexOf(' async function compressed'),source.indexOf(' function decodeFrames'))+';this.read=compressed;',ctx);
(async()=>{
 const asset={file:'immutable.gz',url:'https://raw.githubusercontent.com/example/immutable.gz',sha256:hash};
 assert.equal((await ctx.read(asset)).verified,true);
 assert(requested.startsWith('data/sangolqui-lahars/immutable.gz?sha='));
 ctx.location.hostname='stevanjazziel-ui.github.io';
 assert.equal((await ctx.read(asset)).verified,true);
 assert(requested.startsWith(asset.url+'?sha='));
 await assert.rejects(()=>ctx.read({...asset,sha256:'0'.repeat(64)}),/diferente/);
 console.log('Actual asset reader: local/public URL selection, gzip and SHA-256 rejection passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
