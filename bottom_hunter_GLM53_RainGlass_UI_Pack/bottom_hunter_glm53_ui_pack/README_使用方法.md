# 怎么直接给 GLM-5.3

最省事的方法：

1. 把整个素材包上传给 GLM-5.3。
2. 如果它一次不能上传 ZIP，就至少上传：
   - MASTER_PROMPT_GLM53.md
   - references/00_TARGET_CONCEPT_RainGlassQuantTerminal.png
   - REFERENCE_ASSETS.md
3. 第一条消息直接粘贴 `SEND_TO_GLM_FIRST.txt` 的内容。
4. 确保 GLM 能访问/打开 `Madong9/bottom-hunter` 仓库，或在本地 agent 中把工作目录指向仓库根目录。
5. 第一轮只接受“架构审计 + 独立 RainGlassDemo”，不要让它直接重写所有正式 GUI。

如果第一版 Demo 视觉不够好，先让它继续调 shader/material，不要急着迁正式页面。
