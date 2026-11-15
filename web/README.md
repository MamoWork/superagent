# Opportunity Scout · Web

本地机会研究工作台的前端：React 19 + TypeScript + Vite，数据全部来自
`../server` 的 FastAPI。没有 mock、没有演示模式；API 未连接时只显示离线状态。

迁移前的单文件原型归档在 `../legacy/opportunity_scout_prototype.html`，
只作历史参考，不参与开发、构建或打包。

## 开发

```bash
npm install
npm run dev          # http://127.0.0.1:5173
```

Vite 把 `/api` 代理到 `http://127.0.0.1:8765`。目标地址可用
`VITE_API_PROXY_TARGET` 覆盖。

后端需要同时运行：

```bash
cd ../server
uvicorn app.main:app --reload --port 8765
```

## 构建与检查

```bash
npm run check        # typecheck + lint + vitest
npm run build        # 输出 dist/，由 FastAPI 同源托管
npm run preview
```

生产模式由 FastAPI 在 `/` 托管 `dist/`，深链（如 `/results/run_x`）由后端
SPA fallback 返回 `index.html`。`dist/assets/*` 带 immutable 缓存头，
`index.html` 每次 `no-store` 并注入运行时配置。

## API 类型

`openapi.json` 是后端提交的 OpenAPI 快照。后端 schema 变化后：

```bash
cd ../server
python scripts/export_openapi.py > ../web/openapi.json
cd ../web
npm run gen:api      # 生成 src/api/schema.d.ts
```

字段使用仍集中在 `src/api/types.ts`，页面不直接依赖生成文件。

## 目录

```
src/
├── api/          fetch client、endpoints、query keys、生成类型
├── app/          AppShell、侧栏、顶栏、路由、错误页
├── components/   弹窗、Toast、Badge、来源选择、状态视图
├── context/      Toast
├── data/         来源目录（与 /providers 合并）
├── features/     new / results / pipeline / schedules / history / library / settings
├── hooks/        useBackend / useRuns / useLibrary / useSchedules
├── lib/          时间、导出、cron、状态映射、人工触达模板
├── styles/       全局 CSS（类名与设计令牌沿用迁移前的单文件原型）
└── test/         Vitest setup
```

## 约束

- 只读采集公开内容；不自动发帖、评论或私信。
- 触达模板在本地按机会快照拼装，标注“非 AI 生成”，只提供复制。
- AI 密钥只来自后端环境变量，前端不收集、不保存。
- 机会库 / 闭环数据存后端 SQLite，不使用 `localStorage`。
- 版本信息、数据源状态、AI 状态都来自真实 API。
