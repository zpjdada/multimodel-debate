---
name: source-search
description: 在没有 websearch 凭据时，用 webfetch 查一手来源并能读正文。适用于论文库（arXiv、ACL、PMLR、NeurIPS）、官方文档与代码仓库、政府与政策网站、标准与技术规范、统计数据库、行业报告。当 websearch 不可用或被取消、但又需要核查某个具体主张时使用。
---

# 无 websearch 时的检索与正文读取

`websearch` 需要已连接的搜索 provider 凭据。没有凭据时仍可用 `webfetch` 直接取页面，
一手来源大多不经过人机验证。每条引用都要记录你实际读到的 URL 与章节。

**先看 `research_brief.md` 指定了什么来源。** 它说是论文就查论文库，说是政策文件、标准、
官方数据库就以那些页面为准。下面四组通道按来源类型选，不是按方便程度选。

## 一、通用：直接打开已知页面

多数一手来源就是一个 HTML 页面，不需要 API：

```
https://www.example.gov.cn/xxgk/zcfg/2025/xxx.html
https://www.iso.org/standard/xxxxx.html
```

- 站点内检索常被 robots 或人机验证挡住，优先用站外的 `site:` 查询或站点自己的站内搜索页。
- 页面有分页或"下一页"时逐页读，不要只读首页就下结论。
- 政府与机构网站常见：正文页、附件 PDF、表格下载。附件往往才是真正的内容，正文页只是通知。
- 版本与生效日期必须记下来。政策、标准、法规都有多个版本，引错年份等于引错证据。

## 二、学术文献

### arXiv 检索（Atom 文本）

```
https://export.arxiv.org/api/query?search_query=all:%22self-speculative+decoding%22&start=0&max_results=20&sortBy=relevance
```

- 换关键词：把 `all:"..."` 改成 `ti:"..."`（标题）或 `abs:"..."`（摘要）。
- 多个词用 `+AND+` 连接，例如 `abs:"layer+skipping"+AND+abs:"8B"`。
- 结果里 `entry/id` 是 abs 页，`entry/published` 是首次提交年份。
- 按编号核对单篇：`https://export.arxiv.org/api/query?id_list=2404.16710`
- 按提交时间查最新：`&sortBy=submittedDate&sortOrder=descending`

### OpenAlex（JSON，覆盖广，不限 arXiv）

```
https://api.openalex.org/works?search=layer%20skipping%20inference&per-page=10&sort=cited_by_count:desc
```
返回题名、年份、DOI、引用数、期刊/会议。适合查非 arXiv 的会议论文与引文网络。

### Crossref / DBLP（元数据，适合查会议版）

```
https://api.crossref.org/works?query.bibliographic=layer+skipping&rows=5
https://dblp.org/search/publ/api?q=layer+skipping&format=json&h=10
```

### Semantic Scholar（JSON，常被 429）

```
https://api.semanticscholar.org/graph/v1/paper/search?query=self-speculative+decoding&limit=20&fields=title,year,abstract,externalIds,citationCount,url
```
返回 429 时停一会儿再试，或改用 arXiv/OpenAlex；不要因为一次 429 就声称检索失败。

### ACL Anthology / 论文集目录

- 目录页：`https://aclanthology.org/events/acl-2024/`
- 站内搜索：`https://aclanthology.org/search/?q=layer+skipping`
- 单篇：`https://aclanthology.org/<id>/`
- NeurIPS：`https://papers.nips.cc/paper_files/paper/<year>/`
- PMLR：`https://proceedings.mlr.press/<volume>/`
- CVF：`https://openaccess.thecvf.com/CVPR2024`

## 三、代码、数据与规范

```
https://api.github.com/search/repositories?q=layerskip+speculative&sort=stars
https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>
https://huggingface.co/api/models?search=layerskip
```
`api.github.com` 有匿名配额（每小时 60 次），打满会返回 403；此时改用
`raw.githubusercontent.com` 直读已知路径。**读 README 不等于读了实现**，
要说清读的是哪个文件、哪一段。

数据集与统计口径：优先官方发布页而不是转载页。引用统计数字时同时写出年份、口径
（分母是什么、统计范围含不含某类对象）与原始表名，否则数字无法被核对。

## 四、读正文（关键：不要停在摘要或摘要页）

落地页通常只有摘要、提要或通知标题。按优先级尝试：

### 1. HTML 正文（首选）

大多数网站本身就是完整正文，直接 `webfetch` 即可，不需要转换。
arXiv 论文用 `https://arxiv.org/html/<id>v<版本>`（例：`https://arxiv.org/html/2404.16710v2`）。
注意域名是 `arxiv.org`，不是 `export.arxiv.org`；只有较新论文有 HTML，404 说明该文没生成。

### 2. ar5iv（老论文的 HTML 版）

```
https://ar5iv.labs.arxiv.org/html/<id>
```
实例：`https://ar5iv.labs.arxiv.org/html/2307.02628` 返回完整正文。
arXiv 官方 HTML 不存在时先试这个。

### 3. r.jina.ai（把 PDF 转成纯文本）

```
https://r.jina.ai/https://aclanthology.org/2022.findings-acl.189.pdf
https://r.jina.ai/https://proceedings.mlr.press/v139/song21a/song21a.pdf
```
返回 Markdown 化的正文，含章节标题、表格与部分公式（公式会失真，涉及具体式子时
以 arXiv HTML 为准）。**这是读非 arXiv 论文与机构 PDF 的通用途径。**
若目标 URL 是摘要页而不是 PDF，转出来也只有摘要，务必拼 `.pdf`。

### 4. 兜底：只拿到元数据时

`https://arxiv.org/abs/<id>` 只有摘要与元数据。用它确认文献存在与版本号，
不能当作读过方法。同理，政策文件的"通知"页不等于附件里的实施办法。

## 五、已知不可用

- `openreview.net` 返回 Cloudflare 人机验证页（"Verifying your browser"）。不要把它
  当作已读，改用该论文在 arXiv 的预印本，并注明读的是哪个版本。
- 知网（`kns.cnki.net`）检索页停在安全验证，正文还要求登录与机构订阅；经 `r.jina.ai`
  走同一地址为 transport error。需要中文文献时请使用者自行下载到 `materials/`。
- `webfetch` 不能直接读 PDF（`Unsupported fetched file content type: application/pdf`），
  必须先经 `r.jina.ai` 转文本。
- `api.semanticscholar.org` 常返回 429。
- 扫描版 PDF 没有文字层时，转出来是空的。遇到空正文要如实报告，不能当作读过。
