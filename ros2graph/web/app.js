import {GraphExplorer} from './graph.js';
import {GraphClient} from './client.js';

const $=id=>document.getElementById(id);
let graph,connected=false,authRequired=false,retryTimer=null,noticeTimer=null;
let connecting=false,attempt=0,prefetched=null;

function showNotice(error) {
  const notice=$('notice');notice.textContent=error.message || String(error);
  notice.classList.add('error');notice.hidden=false;
  clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>{notice.hidden=true;},6000);
}
function showAccess(show) {
  $('access-form').hidden=!show;
  $('connection-access').setAttribute('aria-expanded',String(show));
  if(show)$('access-token').focus({preventScroll:true});
}
function status(label,state) {
  $('connection-status').textContent=label;
  $('connection-status').parentElement.dataset.state=state;
}
function scheduleReconnect() {
  clearTimeout(retryTimer);
  if(!connected && !authRequired && !document.hidden)
    retryTimer=setTimeout(()=>{void connect();},2000);
}
const client=new GraphClient({onState:state=>{
  connected=state.connected;authRequired=Boolean(state.error?.unauthorized);
  graph?.setConnected(connected);
  if(connected) {
    clearTimeout(retryTimer);status('Connected','connected');
  } else {
    status(authRequired?'Token required':'Disconnected',authRequired?'unauthorized':'disconnected');
    if(authRequired) {
      $('access-error').textContent=state.error.message;
      if($('access-form').hidden)showAccess(true);
    }
    scheduleReconnect();
  }
}});
graph=new GraphExplorer({
  request:(path,body)=>{
    if(path==='/api/graph' && body===undefined && prefetched) {
      const value=prefetched;prefetched=null;return Promise.resolve(value);
    }
    return client.request(path,body);
  },
  onError:showNotice,
});
graph.setVisible(true);

async function connect() {
  const current=++attempt;connecting=true;prefetched=null;
  clearTimeout(retryTimer);status('Connecting…','connecting');
  $('connection-retry').disabled=true;$('access-error').textContent='';
  try {
    const snapshot=await client.request('/api/graph');
    if(current!==attempt)return;
    graph.setConnected(true);
    $('access-clear').hidden=!client.hasToken;showAccess(false);
    // An existing refresh already owns the next render; never keep this
    // snapshot around to replay during a later polling interval.
    if(!graph.pending) {prefetched=snapshot;await graph.refresh();}
  } catch(error) {
    if(current!==attempt)return;
    if(!graph.data)graph.message(error.message);
    $('graph-meta').textContent=error.message;
  } finally {
    if(current===attempt) {
      connecting=false;$('connection-retry').disabled=false;
      scheduleReconnect();
    }
  }
}

$('connection-retry').onclick=()=>void connect();
$('connection-access').onclick=()=>showAccess($('access-form').hidden);
$('access-form').onsubmit=event=>{
  event.preventDefault();client.setToken($('access-token').value);$('access-token').value='';
  authRequired=false;connected=false;graph.setConnected(false);void connect();
};
$('access-clear').onclick=()=>{
  client.setToken('');$('access-token').value='';$('access-clear').hidden=true;
  authRequired=false;connected=false;graph.setConnected(false);void connect();
};
document.addEventListener('visibilitychange',()=>{
  if(document.hidden)clearTimeout(retryTimer);
  else if(!connected && !authRequired && !connecting)void connect();
});
// Suspending visibility also releases this page's observation lease. Keep the
// explorer available for pages restored from the browser's back-forward cache.
window.addEventListener('pagehide',()=>{clearTimeout(retryTimer);graph.setVisible(false);});
window.addEventListener('pageshow',()=>{
  graph.setVisible(true);
  if(!connected && !authRequired && !connecting)void connect();
  else if(connected && !connecting)void graph.refresh();
});
void connect();
