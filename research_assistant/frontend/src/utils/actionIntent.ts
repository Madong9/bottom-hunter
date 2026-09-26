const INVESTMENT_ACTION_PATTERNS = [
  /可以买(?:了|吗|么)?/,
  /(?:现在)?能买(?:吗|么)?/,
  /该买还是卖/,
  /应该买哪个/,
  /现在(?:是|算不算|是不是).*买点/,
  /(?:建议|推荐).*(?:买入|卖出)/,
  /(?:应该|要不要|是否).*(?:买入|卖出)/,
  /买哪只/,
];

export function requiresInvestmentConfirmation(question: string): boolean {
  const normalized = question.replace(/\s+/g, "");
  return INVESTMENT_ACTION_PATTERNS.some((pattern) => pattern.test(normalized));
}
