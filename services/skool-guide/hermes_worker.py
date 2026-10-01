"""One isolated Hermes turn per process: no shared user memory or generic tools."""
import os,sys,json
sys.path.insert(0,os.environ.get('HERMES_RUNTIME','/usr/local/lib/hermes-agent'))
from run_agent import AIAgent
request=json.load(sys.stdin)
agent=AIAgent(model=os.environ.get('GUIDE_MODEL','openai/gpt-4.1-mini'),provider='openrouter',base_url='https://openrouter.ai/api/v1',api_key=os.environ['OPENROUTER_API_KEY'],enabled_toolsets=[],max_iterations=2,max_tokens=2200,quiet_mode=True,save_trajectories=False,skip_context_files=True,skip_memory=True,skip_background_review=True,load_soul_identity=False,run_budget_seconds=75,ephemeral_system_prompt=request['system'])
if agent.tools:
    agent.close()
    raise RuntimeError('Unexpected tools enabled in public guide')
try:
    result=agent.run_conversation(request['message'])
    print('\nBRAINVIEW_RESULT:'+json.dumps({'text':result['final_response']},ensure_ascii=False))
finally:agent.close()
