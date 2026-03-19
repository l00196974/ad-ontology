const { AgentFactory } = require('./dist/services/agent-factory.js');

async function test() {
  const agentFactory = new AgentFactory('../../../skills');
  const agent = agentFactory.createAgent();
  
  const stream = await agent.stream(
    { messages: [{ role: 'user', content: '你好' }] },
    { streamMode: 'values' }
  );
  
  console.log('=== Stream Events ===');
  for await (const event of stream) {
    console.log('Event keys:', Object.keys(event));
    console.log('Event:', JSON.stringify(event, null, 2).slice(0, 500));
    console.log('---');
  }
}

test().catch(console.error);
