# Acceptance Checklist — Crystal Clear Rain Glass

## 必须 PASS

### 透明玻璃
- [ ] 玻璃无明显黑/蓝/青底色
- [ ] 背景透过玻璃可辨认
- [ ] 卡片不是 dark acrylic
- [ ] 边缘有细小高光
- [ ] blur 轻微而真实
- [ ] refraction 克制

### 水滴
- [ ] 70%+ 水滴直径约 1.5~4px
- [ ] 绝大多数 <10px
- [ ] 大滴极少，约 18~30px
- [ ] 最大不超过约 35px
- [ ] 水滴基本无色透明
- [ ] 能观察到背后 UI 的局部折射
- [ ] 无 sphere mesh / orb / bubble
- [ ] 无 cyan 实体球
- [ ] 不覆盖核心数据

### 性能
- [ ] High/Balanced/Low 都能切
- [ ] High 目标 60 FPS
- [ ] 失焦降低刷新
- [ ] 最小化暂停
- [ ] Qt RHI / OpenGL / Vulkan 等 GPU backend 可验证

### 工程
- [ ] 不用 CUDA
- [ ] 不用 PyTorch/TensorFlow/CuPy
- [ ] 不重写业务逻辑
- [ ] 不提前重写 K线
- [ ] CI 无 GPU 可跑
- [ ] tests 通过

### 本轮范围
- [ ] 只完成 PHASE 0 / PHASE 1
- [ ] 正式 GUI 未开始大规模迁移
- [ ] 提供实际截图
- [ ] 提供 FPS/backend
- [ ] 完成后停下来等待验收
