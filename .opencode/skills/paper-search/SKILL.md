---
name: paper-search
description: 在没有 websearch 凭据时，用 webfetch 查论文与代码的一手资料，并能把 PDF 正文转成文本。适用于 arXiv、ACL Anthology、NeurIPS/ICML/ICLR 论文集、GitHub 仓库。当 websearch 不可用或被取消、但又需要核查最相近工作时使用。
---

# 无 websearch 时的论文检索与正文读取

`websearch` 需要已连接的搜索 provider 凭据。没有凭据时仍可用 `webfetch` 直接查 API，
这些端点返回纯文本或 JSON，不经过人机验证。每条引用都要记录你实际读到的 URL 与章节。

## 一、检索（找到论文）

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

## 二、读正文（关键：不要停在摘要）

出版方落地页通常只有摘要。以下三条路能读到方法段，按优先级使用：

### 1. arXiv HTML（首选，完整方法 + 公式）

```
https://arxiv.org/html/<id>v<版本>      例：https://arxiv.org/html/2404.16710v2
```
注意域名是 `arxiv.org`，不是 `export.arxiv.org`。只有较新论文有 HTML；
报 404 说明该文没生成 HTML，改用下一条。

### 2. ar5iv（老论文的 HTML 版，覆盖 2020 年后大量论文）

```
https://ar5iv.labs.arxiv.org/html/<id>
```
实例：`https://ar5iv.labs.arxiv.org/html/2307.02628` 返回完整正文。
arXiv 官方 HTML 不存在时先试这个。

### 3. r.jina.ai（能把 PDF 转成纯文本，通吃 ACL / PMLR / NeurIPS）

```
https://r.jina.ai/https://aclanthology.org/2022.findings-acl.189.pdf
https://r.jina.ai/https://proceedings.mlr.press/v139/song21a/song21a.pdf
```
返回的是 Markdown 化的正文，含章节标题、表格与部分公式（公式会失真，涉及具体式子时
以 arXiv HTML 为准）。**这是读非 arXiv 论文方法段的唯一实用途径。**
若目标 URL 是摘要页而不是 PDF，转出来也只有摘要，务必拼 `.pdf`。

### 4. 兜底：abs 页

```
https://arxiv.org/abs/<id>
```
只有摘要与元数据。用它确认论文存在与版本号，不能当作读过方法。

## 三、代码与实现核查

```
https://api.github.com/search/repositories?q=layerskip+speculative&sort=stars
https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path>
https://huggingface.co/api/models?search=layerskip
```
`api.github.com` 有匿名配额（每小时 60 次），打满会返回 403；此时改用
`raw.githubusercontent.com` 直读已知路径。**读 README 不等于读了实现**，
要说清读的是哪个文件、哪一段。

## 四、已知不可用

- `openreview.net` 返回 Cloudflare 人机验证页（"Verifying your browser"）。不要把它
  当作已读，改用该论文在 arXiv 的预印本，并注明读的是哪个版本。
- `webfetch` 不能直接读 PDF（`Unsupported fetched file content type: application/pdf`），
  必须先经 `r.jina.ai` 转文本。
- `api.semanticscholar.org` 常返回 429。
