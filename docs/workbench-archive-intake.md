# 工作台上传作图包

现有工作台可接入 `workbench/archive-intake.mjs` 的同源上传接口，继续调用
`scripts/new-delivery-folders.ps1` 建目录，不另建收包引擎。网页入口为“上传作图包”。

## 用户操作

1. 选择 ZIP/RAR。文件名含月份、编辑、篇数时自动填入，提交前可改。
2. 点击“上传并登记”。先显示传输进度，再核对实际 Word 数量、来源和已有目录。
3. 成功后作者按编辑分组立即出现。同一作者多篇按文章标题区分。

登记不启动整批制图，不代表逐图或整批验收。未开始的文章为“未完成”，无图文章不能因空数组判断为通过。
原始压缩包保留在用户指定交付批次内，作者目录不填候选稿。内部只提取 Word 供查看；附件仍完整保留在原包中，后续生产按来源核对后提取。

## 数据和重复提交

- 状态保存在仓库外 `archive-intake/batches.json`，原包 SHA256 为批次去重依据。
- 文章身份为原包 SHA256 + 包内完整 Word 路径，不按作者姓名配对。
- 同包重复提交返回原登记；填写的月份/编辑/篇数冲突时报错。现有同批次不同原包拒绝覆盖。
- 现有 Word 哈希不同也拒绝覆盖。目录建立失败时不登记文章；保留的同哈希目录可安全重试。
- 不能识别的 Word 文件名、实际篇数不符、路径穿越、过大文件均拒绝。默认最大包 512 MiB、单个 Word 100 MiB、Word 总量 512 MiB、成员数 10000。
- 上传临时文件只存在于本次请求的随机子目录，结束后清理；原包和来源不清理。失败详情保存在内部 `last-error.json`。

## 现有工作台适配

运行时路径配置不进仓库。配置字段：`internalRoot`、`deliveryRoot`、`powershell`、`folderScript`，可选 `unrar`、`maxBytes`、`relatedReviews`（管理员配置的已有本机工作台 URL）。

在已有 HTTP 适配器中：

```js
const intake = createArchiveIntake({
  config, root: path.join(stateRoot, 'archive-intake'), origin,
  register: batch => registerArchiveArticles({articles, link, wordTokens}, batch)
});
// 在通用 POST 拒绝分支之前：
if (intake.handle(req, res, url)) return;
// /data 中先同步既有工作台状态；保留最后成功同步结果，应显示离线提醒：
await syncRelatedReviews(articles, config.relatedReviews,
  path.join(stateRoot, 'archive-intake', 'related-cache.json'));
```

适配器不得重算带 `archiveHash` 的空图文章为通过。现有图件来源如仍由另一工作台维护，以完整 Word 路径关联并显示 `externalReviewUrl`“打开已有图件”；该页面仍是图稿、批注和验收的唯一写入处，不复制或迁移验收。失联保留上次状态并明确注明，不能重置未完成。此桥接不是整合后的制图队列。

首页加入 `#archive-intake-open` 按钮并加载 `archive-intake.css` / `archive-intake-ui.js`；服务端按同源静态资源提供这两项。UI 沿用当前 Tabler 组件。`registerArchiveArticles` 的 `link` 使用原工作台文件白名单生成链接，不能放开任意路径读取。

部署后须验证真实上传、重复提交、重启恢复、旧状态未变化和已有图件链接。单图修订后台另见 [workbench-revision-jobs.md](workbench-revision-jobs.md)；收包不暗中提交修订任务。
