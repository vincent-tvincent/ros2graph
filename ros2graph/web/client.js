// Same-origin graph transport. Credentials never enter browser storage or URLs.
const ROUTES = new Map([
  ['/api/graph', 'GET'],
  ['/api/graph/watch', 'POST'],
  ['/api/graph/sample', 'POST'],
]);

export class GraphApiError extends Error {
  constructor(message, status=0) {
    super(message);
    this.name='GraphApiError';
    this.status=status;
    this.unauthorized=status===401;
  }
}

export class GraphClient {
  constructor({fetchImpl=globalThis.fetch.bind(globalThis), onState=()=>{}, timeoutMs=10000}={}) {
    this.fetchImpl=fetchImpl;this.onState=onState;this.timeoutMs=timeoutMs;
    this.token='';this.revision=0;this.disposed=false;this.active=new Set();
  }
  get hasToken() { return Boolean(this.token); }
  setToken(value) {
    this.token=typeof value==='string'?value.trim():'';
    this.revision++;
    // Retired watch requests still return their lease IDs for scoped cleanup.
    for(const pending of this.active)if(pending.method==='GET')pending.controller.abort();
  }
  async request(path,body) {
    if(this.disposed)throw new GraphApiError('Connection closed.');
    const method=body===undefined?'GET':'POST';
    if(ROUTES.get(path)!==method)throw new GraphApiError('Unsupported graph request.');
    const revision=this.revision,controller=new AbortController();
    const release=path==='/api/graph/watch' && body?.operation==='release';
    const pending={controller,method,release};this.active.add(pending);
    let timedOut=false;
    const timer=setTimeout(()=>{timedOut=true;controller.abort();},this.timeoutMs);
    const headers={Accept:'application/json'};
    if(body!==undefined)headers['Content-Type']='application/json';
    if(this.token)headers.Authorization='Bearer '+this.token;
    try {
      const response=await this.fetchImpl(path,{method,headers,cache:'no-store',credentials:'omit',
        mode:'same-origin',signal:controller.signal,keepalive:release,
        ...(body===undefined?{}:{body:JSON.stringify(body)})});
      const text=await response.text();
      let value;
      try{value=JSON.parse(text);}catch{}
      if(!response.ok) {
        const detail=typeof value?.reason==='string'?value.reason:typeof value?.message==='string'?value.message:
          typeof value?.error==='string'?value.error:'';
        throw new GraphApiError(detail.slice(0,240) ||
          (response.status===401?'An access token is required or was not accepted.':`Graph request failed (${response.status}).`),response.status);
      }
      if(value===undefined)throw new GraphApiError('The server did not return graph JSON.',response.status);
      if(path==='/api/graph' && revision===this.revision && !this.disposed)
        this.onState({connected:true,error:null});
      return value;
    } catch(cause) {
      const error=cause instanceof GraphApiError?cause:new GraphApiError(
        timedOut?'The graph server did not respond in time.':controller.signal.aborted?
          'Connection request cancelled.':'The graph server could not be reached.');
      if(revision===this.revision && !this.disposed && (path==='/api/graph' || error.unauthorized))
        this.onState({connected:false,error});
      throw error;
    } finally {
      clearTimeout(timer);this.active.delete(pending);
    }
  }
  dispose() {
    this.disposed=true;this.revision++;this.token='';
    for(const pending of this.active)if(!pending.release)pending.controller.abort();
  }
}
