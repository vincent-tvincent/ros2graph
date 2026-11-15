"""Names and process/domain environment never substitute for exact GID proof."""
import copy

from ros2graph.rpc_trace import RpcTraceCounters,INIT_EVENTS,RPC_PHASES
from ros2graph.graph_rpc import verify_rpc_domain,service_activity
from test_rpc_trace import Clock


def traced_pair():
    clock=Clock();c=RpcTraceCounters(clock=clock);c.set_ready(True);c.set_active('viewer',True)
    # Two contexts in one process can own identical names in different domains.
    for handle,gid,calls in ((1,b'\x01\x02',3),(2,b'\x03\x04',30)):
        c.ingest('ros2:rcl_node_init',10,clock(),{'node_handle':handle,'node_name':'same','node_namespace':'/example'})
        c.ingest('ros2:rmw_publisher_init',10,clock(),{'rmw_publisher_handle':handle+100,'gid':gid})
        c.ingest('ros2:rcl_publisher_init',10,clock(),{'node_handle':handle,'rmw_publisher_handle':handle+100,'topic_name':'/example/proof'})
        c.ingest('ros2:rcl_service_init',10,clock(),{'node_handle':handle,'rmw_service_handle':handle+200,'service_name':'/example/query'})
        for _ in range(calls):
            c.ingest('ros2:rmw_take_request',10,clock(),{'rmw_service_handle':handle+200,'taken':True})
    clock.value+=1_000_000_000
    return c.snapshot()


def visible(gid='0102',kind='publishers'):
    return [{'name':'/example/proof',kind:[{'gid':gid,'node_id':'node:/example/same'}]}]


def test_identical_fqn_and_pid_in_different_domains_are_separated_by_node_handle_gid_proof():
    source=traced_pair();before=copy.deepcopy(source)
    selected=verify_rpc_domain(source,visible())
    assert len(source['endpoints'])==2 and len(source['nodes'])==2
    assert len(selected['endpoints'])==1
    assert selected['endpoints'][0]['channels']['request_received']['messages']==3
    metric=service_activity({'name':'/example/query','servers':['node:/example/same'],'clients':[]},selected)
    assert metric['requests']['messages']==3
    assert source==before
    assert selected['domain_verification']['excluded_unverified_endpoints']==1
    assert selected['domain_verification']['name_only_matching'] is False


def test_missing_mismatched_or_ambiguous_proof_never_manufactures_zero():
    for change in ('absent','kind','topic','gid','duplicate_node_id','pid','fqn'):
        source=traced_pair();topics=visible()
        if change=='absent':source.pop('nodes')
        elif change=='kind':topics=visible(kind='subscriptions')
        elif change=='topic':topics[0]['name']='/another/topic'
        elif change=='gid':topics=visible('abcd')
        elif change=='duplicate_node_id':source['nodes'].append(copy.deepcopy(source['nodes'][0]))
        elif change=='pid':source['endpoints'][0]['pid']=999
        elif change=='fqn':source['endpoints'][0]['node_fqn']='/another/node'
        selected=verify_rpc_domain(source,topics)
        assert selected['endpoints']==[],change
        metric=service_activity({'name':'/example/query','servers':['node:/example/same'],'clients':[]},selected)
        assert metric['messages'] is None and metric['rate_hz'] is None,change


def test_node_handle_reuse_does_not_inherit_retired_topic_gid_proof():
    clock=Clock();c=RpcTraceCounters(clock=clock);c.set_ready(True)
    c.ingest('ros2:rcl_node_init',10,clock(),{'node_handle':1,'node_name':'old','node_namespace':'/'})
    c.ingest('ros2:rmw_subscription_init',10,clock(),{'rmw_subscription_handle':10,'gid':b'\x01'})
    c.ingest('ros2:rcl_subscription_init',10,clock(),{'node_handle':1,'rmw_subscription_handle':10,'topic_name':'/proof'})
    assert c.snapshot()['nodes'][0]['topic_endpoints']
    clock.value+=1
    c.ingest('ros2:rcl_node_init',10,clock(),{'node_handle':1,'node_name':'new','node_namespace':'/'})
    assert c.snapshot()['nodes'][0]['topic_endpoints']==[]


def test_missing_rpc_tracepoint_declarations_make_only_unsupported_phase_unknown():
    clock=Clock();c=RpcTraceCounters(clock=clock);c.set_ready(True);c.set_active('viewer',True)
    c.ingest('ros2:rcl_node_init',10,clock(),{'node_handle':1,'node_name':'node','node_namespace':'/'})
    c.ingest('ros2:rcl_service_init',10,clock(),{'node_handle':1,'rmw_service_handle':2,'service_name':'/query'})
    c.set_tracepoints(set((*INIT_EVENTS,*RPC_PHASES))-{'ros2:rmw_send_response'})
    clock.value+=1_000_000_000;snapshot=c.snapshot();channels=snapshot['endpoints'][0]['channels']
    assert snapshot['state']=='partial'
    assert channels['request_received']['messages']==0
    assert channels['response_sent']['messages'] is None and channels['response_sent']['rate_hz'] is None


def test_requested_rpc_mapping_budget_is_honored_above_old_256_default():
    assert RpcTraceCounters(max_endpoints=512).max_endpoints==512
