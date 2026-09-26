import { describe, expect, it } from "vitest";
import { requiresInvestmentConfirmation } from "./actionIntent";

describe("requiresInvestmentConfirmation", () => {
  it.each([
    "贵州茅台现在可以买了吗",
    "茅台现在能买吗？",
    "宁德时代该买还是卖",
    "贵州茅台和宁德时代应该买哪个",
    "Apple 现在是不是买点",
  ])("行动意图需要用户确认：%s", (question) => {
    expect(requiresInvestmentConfirmation(question)).toBe(true);
  });

  it.each([
    "分析贵州茅台的基本面和估值",
    "宁德时代近期有什么新闻和风险",
    "比较贵州茅台和宁德时代",
  ])("普通研究问题直接进入分析：%s", (question) => {
    expect(requiresInvestmentConfirmation(question)).toBe(false);
  });
});
