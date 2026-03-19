/**
 * 对比测试脚本：原版后端 vs DeepAgents 后端
 */

const ORIGINAL_URL = 'http://localhost:3100';
const DEEPAGENTS_URL = 'http://localhost:3200';

const TEST_CASES = [
  {
    name: '简单问候',
    message: '你好',
  },
  {
    name: '查询广告数据',
    message: '帮我查询最近7天的广告点击数据',
  },
  {
    name: '诊断问题',
    message: '我的广告点击率突然下降了，帮我诊断一下原因',
  },
];

async function testBackend(url, testCase) {
  const sessionId = `test-${Date.now()}`;
  const startTime = Date.now();

  try {
    const response = await fetch(`${url}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        sessionId,
        message: testCase.message,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let contentChunks = [];
    let toolCalls = [];
    let errors = [];
    let done = false;

    while (!done) {
      const { value, done: streamDone } = await reader.read();
      done = streamDone;

      if (value) {
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));

              if (event.type === 'content') {
                contentChunks.push(event.content);
              } else if (event.type === 'tool_start') {
                toolCalls.push({
                  tool: event.tool,
                  args: event.args,
                  startTime: event.startTime,
                });
              } else if (event.type === 'tool_result') {
                const toolCall = toolCalls.find(t => !t.duration);
                if (toolCall) {
                  toolCall.duration = event.duration;
                  toolCall.status = event.status;
                }
              } else if (event.type === 'error') {
                errors.push(event.error);
              } else if (event.type === 'done') {
                done = true;
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }
    }

    const endTime = Date.now();
    const totalTime = endTime - startTime;

    return {
      success: true,
      totalTime,
      contentLength: contentChunks.join('').length,
      toolCallsCount: toolCalls.length,
      toolCalls,
      errors,
    };
  } catch (error) {
    const endTime = Date.now();
    return {
      success: false,
      totalTime: endTime - startTime,
      error: error.message,
    };
  }
}

async function runComparison() {
  console.log('='.repeat(80));
  console.log('对比测试：原版后端 vs DeepAgents 后端');
  console.log('='.repeat(80));
  console.log();

  for (const testCase of TEST_CASES) {
    console.log(`\n📋 测试用例: ${testCase.name}`);
    console.log(`   消息: ${testCase.message}`);
    console.log('-'.repeat(80));

    // 测试原版后端
    console.log('\n🔵 原版后端 (端口 3100):');
    const originalResult = await testBackend(ORIGINAL_URL, testCase);

    if (originalResult.success) {
      console.log(`   ✅ 成功`);
      console.log(`   ⏱️  总耗时: ${originalResult.totalTime}ms`);
      console.log(`   📝 内容长度: ${originalResult.contentLength} 字符`);
      console.log(`   🔧 工具调用: ${originalResult.toolCallsCount} 次`);
      if (originalResult.toolCalls.length > 0) {
        originalResult.toolCalls.forEach((tc, i) => {
          console.log(`      ${i + 1}. ${tc.tool} (${tc.duration}ms) - ${tc.status}`);
        });
      }
      if (originalResult.errors.length > 0) {
        console.log(`   ❌ 错误: ${originalResult.errors.join(', ')}`);
      }
    } else {
      console.log(`   ❌ 失败: ${originalResult.error}`);
    }

    // 等待1秒
    await new Promise(resolve => setTimeout(resolve, 1000));

    // 测试 DeepAgents 后端
    console.log('\n🟢 DeepAgents 后端 (端口 3200):');
    const deepagentsResult = await testBackend(DEEPAGENTS_URL, testCase);

    if (deepagentsResult.success) {
      console.log(`   ✅ 成功`);
      console.log(`   ⏱️  总耗时: ${deepagentsResult.totalTime}ms`);
      console.log(`   📝 内容长度: ${deepagentsResult.contentLength} 字符`);
      console.log(`   🔧 工具调用: ${deepagentsResult.toolCallsCount} 次`);
      if (deepagentsResult.toolCalls.length > 0) {
        deepagentsResult.toolCalls.forEach((tc, i) => {
          console.log(`      ${i + 1}. ${tc.tool} (${tc.duration}ms) - ${tc.status}`);
        });
      }
      if (deepagentsResult.errors.length > 0) {
        console.log(`   ❌ 错误: ${deepagentsResult.errors.join(', ')}`);
      }
    } else {
      console.log(`   ❌ 失败: ${deepagentsResult.error}`);
    }

    // 对比结果
    if (originalResult.success && deepagentsResult.success) {
      console.log('\n📊 对比结果:');
      const timeDiff = deepagentsResult.totalTime - originalResult.totalTime;
      const timeDiffPercent = ((timeDiff / originalResult.totalTime) * 100).toFixed(1);

      if (timeDiff > 0) {
        console.log(`   ⏱️  DeepAgents 慢了 ${timeDiff}ms (${timeDiffPercent}%)`);
      } else {
        console.log(`   ⏱️  DeepAgents 快了 ${Math.abs(timeDiff)}ms (${Math.abs(timeDiffPercent)}%)`);
      }

      const contentDiff = deepagentsResult.contentLength - originalResult.contentLength;
      if (contentDiff !== 0) {
        console.log(`   📝 内容长度差异: ${contentDiff > 0 ? '+' : ''}${contentDiff} 字符`);
      }

      const toolCallsDiff = deepagentsResult.toolCallsCount - originalResult.toolCallsCount;
      if (toolCallsDiff !== 0) {
        console.log(`   🔧 工具调用差异: ${toolCallsDiff > 0 ? '+' : ''}${toolCallsDiff} 次`);
      }
    }

    console.log('\n' + '='.repeat(80));

    // 等待2秒再进行下一个测试
    await new Promise(resolve => setTimeout(resolve, 2000));
  }

  console.log('\n✅ 对比测试完成！\n');
}

// 运行测试
runComparison().catch(console.error);
