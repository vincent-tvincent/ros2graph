import test from 'node:test';
import assert from 'node:assert/strict';
import {GraphApiError, GraphClient} from '../ros2graph/web/client.js';
import {graphClientId} from '../ros2graph/web/graph.js';

const response=(value,status=200)=>({ok:status>=200&&status<300,status,text:async()=>JSON.stringify(value)});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return{promise,resolve,reject};};

test('graph transport uses same-origin JSON routes without credentials by default',async()=>{
  const calls=[],states=[];
  const client=new GraphClient({fetchImpl:async(...args)=>{calls.push(args);return response({schema_version:1});},onState:state=>states.push(state)});
  await client.request('/api/graph');
  await client.request('/api/graph/sample',{topic:'/example',duration_s:5});
  assert.equal(calls[0][1].method,'GET');assert.equal(calls[0][1].body,undefined);
  assert.equal(calls[0][1].headers.Authorization,undefined);
  assert.equal(calls[0][1].credentials,'omit');assert.equal(calls[0][1].mode,'same-origin');
  assert.equal(calls[0][1].cache,'no-store');
  assert.equal(calls[1][1].method,'POST');assert.equal(calls[1][1].headers['Content-Type'],'application/json');
  assert.deepEqual(JSON.parse(calls[1][1].body),{topic:'/example',duration_s:5});
  assert.deepEqual(states,[{connected:true,error:null}]);assert.equal(client.active.size,0);
});

test('bearer stays in request headers and can be removed without browser storage',async t=>{
  const previous=Object.getOwnPropertyDescriptor(globalThis,'localStorage');
  Object.defineProperty(globalThis,'localStorage',{get(){throw Error('Credentials must never use storage');},configurable:true});
  t.after(()=>{if(previous)Object.defineProperty(globalThis,'localStorage',previous);else delete globalThis.localStorage;});
  const calls=[],client=new GraphClient({fetchImpl:async(...args)=>{calls.push(args);return response({schema_version:1});}});
  client.setToken('  private-token  ');assert.equal(client.hasToken,true);
  await client.request('/api/graph');client.setToken('');await client.request('/api/graph');
  assert.equal(calls[0][0],'/api/graph');assert.equal(calls[0][1].headers.Authorization,'Bearer private-token');
  assert.equal(calls[1][1].headers.Authorization,undefined);assert.equal(client.hasToken,false);
});

test('unexpected URLs and methods are rejected before any credential-bearing fetch',async()=>{
  let calls=0;const client=new GraphClient({fetchImpl:async()=>{calls++;return response({});}});client.setToken('secret');
  for(const [path,body] of [['https://other.invalid/api/graph'],['/api/robot'],['/api/graph',{}],['/api/graph/watch']])
    await assert.rejects(client.request(path,body),/Unsupported graph request/);
  assert.equal(calls,0);
});

test('authentication failures are distinguishable while a rejected sample does not disconnect discovery',async()=>{
  const states=[];let code=400;
  const client=new GraphClient({fetchImpl:async()=>response({reason:'Request rejected'},code),onState:value=>states.push(value)});
  await assert.rejects(client.request('/api/graph/sample',{topic:'/missing'}),error=>error instanceof GraphApiError&&error.status===400);
  assert.equal(states.length,0);
  code=403;await assert.rejects(client.request('/api/graph/watch',{operation:'acquire'}),error=>error.unauthorized===false);
  assert.equal(states.length,0);
  code=401;await assert.rejects(client.request('/api/graph'),error=>error.unauthorized===true);
  assert.equal(states.length,1);assert.equal(states[0].connected,false);assert.equal(states[0].error.status,401);
});

test('a retired credential response cannot change the current connection state',async()=>{
  const pending=deferred(),states=[];let signal;
  const client=new GraphClient({fetchImpl:async(path,options)=>{signal=options.signal;return pending.promise;},onState:value=>states.push(value)});
  client.setToken('first');const request=client.request('/api/graph');client.setToken('second');
  assert.equal(signal.aborted,true);
  pending.resolve(response({schema_version:1}));await request;
  assert.deepEqual(states,[]);assert.equal(client.active.size,0);
});

test('late watch acquisition returns its lease ID after token change for exact scoped cleanup',async()=>{
  const pending=deferred();let signal;
  const client=new GraphClient({fetchImpl:async(path,options)=>{signal=options.signal;return pending.promise;}});
  client.setToken('first');const request=client.request('/api/graph/watch',{operation:'acquire',client_id:'uuid'});
  client.setToken('second');assert.equal(signal.aborted,false);
  pending.resolve(response({accepted:true,lease_id:'old-lease'}));
  assert.equal((await request).lease_id,'old-lease');
});

test('network failure and timeout report unavailable discovery and clear request state',async()=>{
  const states=[],client=new GraphClient({fetchImpl:async()=>{throw new TypeError('Network failed');},onState:s=>states.push(s)});
  await assert.rejects(client.request('/api/graph'),/could not be reached/);
  assert.equal(states[0].connected,false);assert.equal(client.active.size,0);
  const timeout=new GraphClient({timeoutMs:5,fetchImpl:(path,{signal})=>new Promise((resolve,reject)=>{
    signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true});
  })});
  await assert.rejects(timeout.request('/api/graph'),/did not respond in time/);assert.equal(timeout.active.size,0);
});

test('dispose aborts pending reads but lets an already-sent keepalive release complete',async()=>{
  const read=deferred(),release=deferred(),options=new Map();
  const client=new GraphClient({fetchImpl:(path,request)=>{
    options.set(path,request);return path==='/api/graph'?read.promise:release.promise;
  }});
  const reading=client.request('/api/graph');
  const releasing=client.request('/api/graph/watch',{operation:'release',lease_id:'owned'});
  client.dispose();assert.equal(client.hasToken,false);
  assert.equal(options.get('/api/graph').signal.aborted,true);
  assert.equal(options.get('/api/graph/watch').signal.aborted,false);
  assert.equal(options.get('/api/graph/watch').keepalive,true);
  read.resolve(response({schema_version:1}));release.resolve(response({accepted:true}));
  await Promise.all([reading,releasing]);await assert.rejects(client.request('/api/graph'),/Connection closed/);
});

test('watch client IDs work on remote HTTP without crypto.randomUUID',()=>{
  assert.equal(graphClientId({randomUUID:()=> 'native-uuid'}),'native-uuid');
  const id=graphClientId({getRandomValues:bytes=>{bytes.forEach((_,i)=>{bytes[i]=i;});return bytes;}});
  assert.equal(id,'00010203-0405-4607-8809-0a0b0c0d0e0f');
  assert.match(id,/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
});
