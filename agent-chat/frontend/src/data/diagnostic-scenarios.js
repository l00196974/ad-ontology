// 诊断场景数据配置
// 与后端 diagnostic-planner 工具的 SOP 配置保持一致

export const diagnosticScenarios = [
  {
    id: 'cost-increase',
    name: '线索成本突增',
    description: '分析CPA突然升高的原因',
    examples: ['为什么CPA突然升高了？', '最近获客成本变贵了', '帮我分析线索成本突增的原因'],
    icon: '💰',
    color: '#ff6b6b'
  },
  {
    id: 'lead-decrease',
    name: '线索量突降',
    description: '分析线索数量突然下降的原因',
    examples: ['线索量为什么突然下降了？', '最近线索数量变少了', '帮我分析线索量下降的问题'],
    icon: '📉',
    color: '#4ecdc4'
  },
  {
    id: 'ctr-decline',
    name: 'CTR下滑',
    description: '分析点击率下降的原因',
    examples: ['点击率为什么下降了？', 'CTR最近表现不好', '帮我分析点击率下滑的原因'],
    icon: '👆',
    color: '#45b7d1'
  },
  {
    id: 'cvr-decline',
    name: 'CVR下滑',
    description: '分析转化率下降的原因',
    examples: ['转化率为什么下降了？', 'CVR最近表现不好', '帮我分析转化率下滑的原因'],
    icon: '🔄',
    color: '#96ceb4'
  },
  {
    id: 'channel-anomaly',
    name: '渠道结构异常',
    description: '分析渠道流量结构变化',
    examples: ['渠道结构有什么异常？', '流量结构发生了什么变化？', '帮我分析渠道结构异常'],
    icon: '🌐',
    color: '#feca57'
  },
  {
    id: 'audience-analysis',
    name: '高潜人群画像分析',
    description: '分析高潜力人群特征和TGI',
    examples: ['高潜人群有什么特征？', '帮我分析高潜人群画像', 'TGI分析结果如何？'],
    icon: '👥',
    color: '#ff9ff3'
  }
];

// 根据关键词匹配诊断场景
export const matchDiagnosticScenario = (message) => {
  const lowerMessage = message.toLowerCase();

  // 成本相关关键词
  if (lowerMessage.includes('cpa') || lowerMessage.includes('成本') ||
      lowerMessage.includes('获客成本') || lowerMessage.includes('变贵')) {
    return diagnosticScenarios.find(s => s.id === 'cost-increase');
  }

  // 线索量相关关键词
  if (lowerMessage.includes('线索量') || lowerMessage.includes('线索数') ||
      lowerMessage.includes('下降') || lowerMessage.includes('减少')) {
    return diagnosticScenarios.find(s => s.id === 'lead-decrease');
  }

  // CTR相关关键词
  if (lowerMessage.includes('ctr') || lowerMessage.includes('点击率')) {
    return diagnosticScenarios.find(s => s.id === 'ctr-decline');
  }

  // CVR相关关键词
  if (lowerMessage.includes('cvr') || lowerMessage.includes('转化率')) {
    return diagnosticScenarios.find(s => s.id === 'cvr-decline');
  }

  // 渠道相关关键词
  if (lowerMessage.includes('渠道') || lowerMessage.includes('流量结构') ||
      lowerMessage.includes('结构异常')) {
    return diagnosticScenarios.find(s => s.id === 'channel-anomaly');
  }

  // 人群相关关键词
  if (lowerMessage.includes('高潜') || lowerMessage.includes('人群') ||
      lowerMessage.includes('tgi') || lowerMessage.includes('画像')) {
    return diagnosticScenarios.find(s => s.id === 'audience-analysis');
  }

  return null;
};