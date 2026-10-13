# GLM-OCR HTTP API — Technical Brief

Research date context: current docs as indexed at research time.
**Method note:** `web_fetch` was **DNS-blocked for every host** in this environment
(`docs.z.ai`, `docs.bigmodel.cn`, `github.com`, `raw.githubusercontent.com`, `r.jina.ai`,
`docs.siliconflow.com`, `api.siliconflow.cn` all returned
`Error: URL hostname "..." resolves to a non-public IP address`).
All findings below therefore come from **search-engine index content** (Exa, Tavily, Keenable,
DDG, Bing) of the official doc pages, plus the vendor's own SDK source and OpenAPI specs.
Where the docs themselves state a fact, confidence is **high**. Nothing here was verified by
executing a live authenticated request.

---

## 1. Does `glm-ocr` exist, and what is the exact model id?

**VERIFIED: yes.** The model id string is exactly **`glm-ocr`** (lowercase, hyphenated).

It is a real 0.9B-parameter multimodal OCR model published by Z.ai / Zhipu, open-weighted
(`zai-org/GLM-OCR` on Hugging Face, Apache-2.0), built on the GLM-V encoder–decoder architecture,
using PP-DocLayout-V3 for layout analysis plus parallel recognition. It is also deployable
locally via vLLM / SGLang / Ollama.

In the layout-parsing OpenAPI spec the field is constrained to a single-value enum:

```
model enum required  Model code: `glm-ocr`  Available options: `glm-ocr`  Example: "glm-ocr"
```

- <https://docs.z.ai/api-reference/tools/layout-parsing>
- <https://docs.bigmodel.cn/api-reference/模型-api/文档解析>
- <https://github.com/zai-org/GLM-OCR>
- <https://huggingface.co/zai-org/GLM-OCR>

Note: `glm-ocr` is **not** the same string as the self-hosted weights repo name
`zai-org/GLM-OCR`, which is what you'd pass to a local vLLM `--served-model-name`. Don't
conflate the two.

---

## 2. Exact endpoint path

**VERIFIED — both hosts use the `/api/paas/v4/` prefix.**

| Host | Full URL |
| --- | --- |
| CN (Zhipu BigModel) | `https://open.bigmodel.cn/api/paas/v4/layout_parsing` |
| Intl (Z.AI) | `https://api.z.ai/api/paas/v4/layout_parsing` |

The path component in the OpenAPI spec is written `POST /paas/v4/layout_parsing`, and the
"general API endpoint" base for Z.AI is `https://api.z.ai/api/` — so the full URL is
`https://api.z.ai/api/paas/v4/layout_parsing`. The premise that the intl base "uses the same
`/api/paas/v4/` prefix" is **correct**.

Authoritative curl from the intl quick-start:

```bash
curl --location --request POST 'https://api.z.ai/api/paas/v4/layout_parsing' \
  --header 'Authorization: Bearer your-api-key' \
  --header 'Content-Type: application/json' \
  --data-raw '{ "model": "glm-ocr", "file": "..." }'
```

The CN endpoint is confirmed independently by the vendor's own SDK constants:

```python
# skills/glmocr/scripts/glm_ocr_cli.py  (zai-org/GLM-OCR)
API_GUIDE_URL   = "https://open.bigmodel.cn/usercenter/apikeys"
DEFAULT_API_URL = "https://open.bigmodel.cn/api/paas/v4/layout_parsing"
```

and by `glmocr/config.yaml`:

```yaml
maas:
  enabled: true
  api_url: https://open.bigmodel.cn/api/paas/v4/layout_parsing
  model: glm-ocr
  api_key: null        # Required! Get from https://open.bigmodel.cn
  verify_ssl: true
```

- <https://docs.z.ai/guides/vlm/glm-ocr>
- <https://docs.z.ai/api-reference/tools/layout-parsing>
- <https://github.com/zai-org/GLM-OCR/blob/main/skills/glmocr/scripts/glm_ocr_cli.py>
- <https://github.com/zai-org/GLM-OCR/blob/main/glmocr/config.yaml>

---

## 3. Request body schema

**VERIFIED for the fields below** (from the OpenAPI spec rendered on the doc pages).
All four of the reported core fields are real; `return_crop_images` and
`need_layout_visualization` are confirmed with explicit defaults.

| Field | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `model` | string (enum) | **yes** | — | Only `glm-ocr` |
| `file` | string | **yes** | — | An http(s) URL **or** a `data:<mime>;base64,...` data URI |
| `return_crop_images` | boolean | no | `false` | "Whether to return screenshot information" |
| `need_layout_visualization` | boolean | no | `false` | "Whether to return detailed layout image result information" |
| `start_page_id` | integer | no | — | "Start page number for parsing when PDF is provided" |
| `end_page_id` | integer | no | — | End page number for parsing when PDF is provided |

Exact doc text captured for the two booleans:

> `return_crop_images` boolean default:false Whether to return screenshot information
> `need_layout_visualization` boolean default:false Whether to return detailed layout image result information
> `start_page_id` integer Start page number for parsing when PDF is provided

- <https://docs.z.ai/api-reference/tools/layout-parsing>

### `request_id` / `user_id` — **UNRESOLVED (likely real, unconfirmed for this endpoint)**

These are standard Zhipu platform-level parameters (they appear on the `chat/completions`
API), but I could **not** retrieve the tail of the layout-parsing parameter table, so I cannot
confirm they are accepted here. The schema table I recovered covered `model`, `file`,
`return_crop_images`, `need_layout_visualization`, `start_page_id`, and reached `end_page_id`.
Anything after that was truncated. **Treat `request_id`/`user_id` as optional-known-to-Zhipu but
unverified on this endpoint.**

### `stream` — **UNRESOLVED, probably NOT accepted**

I found no evidence of a `stream` parameter on `layout_parsing`. The CN "解析结果" page shows a
separate **async task** pattern (`status`, `task_id`, `parsing_result_url`) used by other Zhipu
document tools, which may be what the `stream` report conflated. Do not implement streaming for
this endpoint without testing.

### Local file upload — **VERIFIED: NOT supported as multipart**

The API accepts **only** an http(s) URL or a base64 data URI in the `file` field. There is no
multipart/form-data upload. The vendor's own SDK confirms this and auto-wraps local paths:

> Input note (MaaS): the upstream API accepts `file` as a URL or a `data:<mime>;base64,...` data
> URI. If you have raw base64 without the `data:` prefix, wrap it as a data URI (recommended).
> The SDK will auto-wrap local file paths / bytes / raw base64 into a data URI when calling MaaS.

- <https://github.com/zai-org/GLM-OCR> (README)

### Response of a `data:` URI requirement

Raw base64 **without** the `data:` prefix is not the documented input form. If you have raw
base64, prepend `data:image/png;base64,` (or the correct MIME) yourself.

---

## 4. Response schema

**VERIFIED for `md_results`, `layout_details`, the `label` enum, and the shape of the tail.**

```jsonc
{
  "id": "...",
  "created": 1234567890,
  "model": "glm-ocr",
  "md_results": "# Doc title\nThis is the document content...",   // STRING (markdown)
  "layout_details": [                                            // object[][] : pages -> elements
    [
      {
        "index": 1,                    // integer, required
        "label": "text",               // enum, required
        "bbox_2d": [0.1, 0.2, 0.9, 0.4],   // normalized 0..1
        "content": "This is the content of the element",
        "height": 800,
        "width": 600
      }
    ]
  ],
  "layout_visualization": [ "" ],
  "data_info": {
    "num_pages": 5,
    "pages": [ { "width": ..., "height": ... } ]
  },
  "usage": { ... }
}
```

### `md_results` — **VERIFIED: a flat STRING**

Doc text is explicit:

> `md_results` string — Recognition result in Markdown format
> Example: `"# Doc title\nThis is the document content..."`

So the report's "plain markdown STRING" is **correct**. Do not expect a list or object.
(Contrast: the *SDK wrapper* `extract_text()` re-shapes things into its own envelope with
`text`, `layout_details`, `ok`, `source` keys — that is a **different layer**. If you call the
HTTP API directly, you get `md_results`, not `text`.)

### `layout_details` — **VERIFIED**

Typed as `object[][]` — an **array of pages, each an array of elements**. Elements have
`index` (integer, required), `label` (enum, required), `content` (string — "Element content
(text / image URL / table HTML)"), and `height`/`width`. Note `content` is polymorphic in
meaning by `label`: plain text for `text`, a URL for `image`, HTML for `table`.

### `label` enum — **VERIFIED, and the report's enum is COMPLETE**

> `layout_details.label` enum required — Element type: **image** for images, **text** for text
> content, **formula** for inline formulas, **table** for tables
> Available options: `image`, `text`, `formula`, `table`

So `{image, text, formula, table}` is exactly right — **there is no `title` value.**

⚠️ **Trap:** you may see `"label": "title"` in examples circulating in blog posts and in the
SDK's `json_result` structure. That comes from **PP-DocLayout-V3 inside the self-hosted SDK
pipeline**, which uses a richer label set (title, etc.). The **hosted HTTP API** normalizes to
the four-value enum. Code against the four values, and defensively tolerate unknown labels
rather than exhausting an enum.

### `bbox_2d` normalization — **partially verified**

The reported "normalized 0..1" is consistent with what I saw, but I could not retrieve an
explicit "normalized" sentence for `bbox_2d` on this page. The vendor SDK contains a
`0-1000 coords` normalization helper for its **local** pipeline, which is a *different*
coordinate space. **Treat the HTTP `bbox_2d` scale as high-confidence-but-not-quotable**;
verify empirically by parsing a known image and checking max values ≤ 1.

- <https://docs.z.ai/api-reference/tools/layout-parsing>
- <https://github.com/zai-org/GLM-OCR/blob/main/skills/glmocr/references/output_schema.md>

---

## 5. Auth header — the one that matters most

**VERIFIED: use `Authorization: Bearer <API_KEY>` on BOTH hosts.**

**The premise that CN requires a bare key with NO `Bearer` prefix appears to be WRONG.**

Evidence:

1. **Intl (api.z.ai)** — quick-start curl is unambiguous:
   `--header 'Authorization: Bearer your-api-key'`
   → <https://docs.z.ai/guides/vlm/glm-ocr>

2. **CN (open.bigmodel.cn)** — the CN OpenAPI spec describes the header as
   **"标准的 HTTP Bearer 认证方式，在 API Keys 页面获取密钥"**
   ("standard HTTP Bearer authentication; obtain the key from the API Keys page").
   → <https://docs.bigmodel.cn/api-reference/模型-api/文档解析>

3. **Third-party mirrors of the same CN spec** render the header example as
   `Bearer {{YOUR_API_KEY}}` (and, in one mirror, mark it optional) — e.g.
   <https://docs.console.zenlayer.com/api-reference/cn/ai/mcpg/ocr/glm-ocr>

4. Every other Zhipu/Z.AI HTTP endpoint documented (chat/completions for glm-4.6v, glm-4.5v,
   glm-5.x) uses `Authorization: Bearer $KEY` on both hosts.

**Residual uncertainty (be honest about it):** I could not execute a live request, so the CN
`Bearer` claim is *documentation-verified, not call-verified*. A bare-key CN mode is not
impossible — the platform has historically accepted `Authorization: <key>` on some CN routes.
See the integration note at the end: store the **raw key** and add the prefix at the header
construction site so flipping it is a one-line change.

- <https://docs.z.ai/guides/vlm/glm-ocr>
- <https://docs.bigmodel.cn/api-reference/模型-api/文档解析>

---

## 6. Limits

### File size — **VERIFIED**

- Single image (JPG, PNG): **≤ 10 MB**
- PDF: **≤ 50 MB**

Doc text, verbatim from both locales of the same page:

> CN: `- PDF、图片（JPG、PNG） - 单图 ≤ 10 MB，PDF ≤ 50 MB - 最大支持 100 页`
> EN: `- PDF, images (JPG, PNG) - Single image ≤ 10MB, PDF ≤ 50MB - Maximum support: 100 pages`

### Max pages — **VERIFIED: 100 on BOTH hosts; the "intl = 30" report is NOT in current docs**

The **same** intl page that would carry the 30-page figure instead says
**"Maximum support: 100 pages"**, and the CN page says **"最大支持 100 页"**. I found no
occurrence of a 30-page limit in current documentation. The conflict resolves in favor of
**100**.

Caveat: docs change, and third-party summaries of this API have cited 100 pages as well
(e.g. <https://cronfeed.work/ai-china-benchmark-eval-notes-zhipu-glm-ocr-layout-first-document-pipeline-2026q2>).
Keep the page cap **configurable** anyway — it is cheap insurance and you will want it for
`start_page_id`/`end_page_id` chunking regardless.

### Input modalities — **VERIFIED**

Only an http(s) URL or a `data:<mime>;base64,...` data URI (see §3). No multipart upload.

- <https://docs.z.ai/guides/vlm/glm-ocr>
- <https://docs.bigmodel.cn/cn/guide/models/vlm/glm-ocr>

---

## 7. Errors and rate limits

### Error response shape — **VERIFIED**

Standard Zhipu error envelope:

```json
{ "error": { "code": "", "message": "" } }
```

(On some routes you'll instead see the flatter
`{"code": "1210", "message": "...", "status": 400}` — the OpenAPI page renders
`{ "code": 123, "message": "" }` for the layout-parsing operation. **Parse defensively: check
for `error.code` / `error.message` first, then fall back to top-level `code`/`message`.**)

### Error codes — **VERIFIED (platform-wide table; applies to this endpoint)**

From <https://docs.z.ai/api-reference/api-code> :

| Code | HTTP | Message |
| --- | --- | --- |
| 1210 | 400 | Invalid API parameter, please check the documentation. |
| 1211 | 400 | Unknown Model, please check the model code. |
| 1212 | 400 | Current model does not support `${method}` call method |
| 1213 | 400 | Parameter `${field}` was not received. |
| 1214 | 400 | Parameter `${field}` is invalid. |
| — | 500 | Internal Error |

A real-world instance of `1210` on a Z.AI-served model, with the flat shape:
`{"message":"400 Invalid API parameter, please check the documentation.","status":400,"code":"1210",...}`
→ <https://github.com/cline/cline/issues/8808>

For **rate limiting**, the platform documents a rate-limit page
(<https://docs.z.ai/api-reference/rate-limit>) but I could not retrieve its contents. **Rate limits
are UNRESOLVED** — implement retry with backoff on 429/5xx rather than hard-coding a limit.

- <https://docs.z.ai/api-reference/api-code>
- <https://docs.z.ai/api-reference/tools/layout-parsing>

---

## 8. Is `glm-ocr` reachable via OpenAI-compatible `chat/completions`?

**VERIFIED: NO — confirmed.**

`glm-ocr` is **not** a chat model. It is exposed **only** through the dedicated
`POST /paas/v4/layout_parsing` operation, whose `model` field is single-valued
`enum: [glm-ocr]`. It appears in the model catalog under document/OCR tooling, separate from
the chat and vision model lineups.

Supporting evidence that it is a distinct API surface, not a chat alias:

- RAGFlow's Zhipu driver advertises `glm-ocr` as an **OCR** model in
  `conf/models/zhipu-ai.json`, but its `ZhipuAIModel.OCRFile` still returns
  `"zhipu, no such method"` — i.e. it is handled as OCR, not chat.
  → <https://github.com/infiniflow/ragflow/issues/15142>
- The Zhipu Python SDK exposes it as a `LayoutParsing` class
  (`ZhipuAiClient...`), not via the chat client.
  → <https://docs.bigmodel.cn/cn/guide/models/vlm/glm-ocr>

**Implication:** you cannot reuse a generic OpenAI client for GLM-OCR. You need a bespoke POST
to `layout_parsing` (see the integration section).

Sending `{"model":"glm-ocr", "messages":[...]}` to `/chat/completions` should yield error
**1211 Unknown Model** (or 1212). **Unverified by execution**, but strongly implied.

---

## 9. FALLBACK: `PaddleOCR-VL-1.5` on SiliconFlow

**VERIFIED: YES — usable via standard OpenAI-compatible `/chat/completions` with `image_url`.**

- **Base URL:** `https://api.siliconflow.cn/v1`
- **Exact model id:** `PaddlePaddle/PaddleOCR-VL-1.5`
- **Cost:** free ($0.00 / $0.00 per 1M tokens)
- **Context:** 16,384 tokens in / 16,384 out
- **Released:** 2026-01-29

SiliconFlow's own launch post confirms it: "硅基流动上线百度 PaddleOCR-VL-1.5，免费调用"
(<https://siliconflow.cn/developer-talk/vo57ggecfisw5shjlyztz1r8>), and the id string is
corroborated by the SiliconFlow-CN entry in models.dev
(<https://models.opencode.ai/providers/siliconflow-cn/>), which lists endpoint
`https://api.siliconflow.cn/v1` with model `PaddlePaddle/PaddleOCR-VL-1.5`.

### Minimal request body

```json
{
  "model": "PaddlePaddle/PaddleOCR-VL-1.5",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "image_url",
          "image_url": { "url": "https://example.com/page.png" } },
        { "type": "text", "text": "OCR:" }
      ]
    }
  ]
}
```

**Task-prefix gotcha (important):** PaddleOCR-VL-1.5 is prompt-steered and expects a task
prefix as the text part. The published task strings are:

```
"ocr":      "OCR:"
"table":    "Table Recognition:"
"formula":  "Formula Recognition:"
"chart":    "Chart Recognition:"
"spotting": "Spotting:"
"seal":     "Seal Recognition:"
```

→ <https://recipes.vllm.ai/PaddlePaddle/PaddleOCR-VL-1.5>

**`detail` parameter:** SiliconFlow's vision docs document a `detail` parameter with values
`low` | `high` | `auto`. Semantics are **inverted from OpenAI's**: for the currently supported
models, omitting it or setting `high` selects high-resolution, while `low` **or `auto`**
selects low-resolution. That differs from OpenAI, where `auto` is the smart default — so
**prefer explicit `"detail": "high"`** rather than relying on `auto`.
→ <https://docs.siliconflow.com/en/userguide/capabilities/vision>

SiliconFlow accepts either an image URL **or** a base64-encoded image in `image_url.url`; for
base64 use a `data:image/png;base64,...` URI.

---

## 10. Zhipu vision models on OpenAI-compatible `chat/completions`

**VERIFIED (with caveats):** `glm-4.6v`, `glm-4.5v`, `glm-4.6v-flash` are real vision models
and **do** work on the OpenAI-compatible chat endpoint at
`https://api.z.ai/api/paas/v4/chat/completions` with an `image_url` content part.

```bash
curl -X POST https://api.z.ai/api/paas/v4/chat/completions \
  -H "Authorization: Bearer $ZAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "glm-4.6v",
    "messages": [{
      "role": "user",
      "content": [
        { "type": "image_url", "image_url": { "url": "https://example.com/a.png" } },
        { "type": "text", "text": "Describe this image." }
      ]
    }]
  }'
```

Model facts:

- `glm-4.6v` — 106B (12B active), 128K context, native multimodal function calling
- `glm-4.6v-flash` — 9B, free, open weights
- `glm-4.5v` — 106B MoE (12B active), image/video/GUI/visual grounding

The full base URL is `https://api.z.ai/api/paas/v4/chat/completions` — note the same
`/api/paas/v4/` prefix as GLM-OCR.

- <https://docs.z.ai/guides/vlm/glm-4.6v>
- <https://docs.z.ai/guides/vlm/glm-4.5v>
- <https://huggingface.co/zai-org/GLM-4.6V>
- <https://github.com/tugudush/copilot-custom-endpoints/blob/main/docs/models/glm.md>
  (independently confirms "OpenAI Chat Completions compatible at
  <https://api.z.ai/api/paas/v4/chat/completions>")

### Reported gotchas — assessment

| Reported gotcha | Verdict |
| --- | --- |
| Plain http(s) image URL accepted | **VERIFIED** — yes, `image_url.url` takes a public URL; base64 data URI also works |
| No `detail` field accepted | **PLAUSIBLE, UNRESOLVED.** Zhipu's vision docs do not document a `detail` parameter for these models; that does not prove the server rejects it. Do **not** send it by default. |
| ≤ 5 MB per image | **UNRESOLVED for Zhipu specifically.** 5 MB is a common inline-image ceiling across vendors, but I could not confirm this number in Zhipu's vision docs. Treat as a safe conservative client-side cap, not a documented limit. |
| Images must be in user messages | **PLAUSIBLE, standard practice.** Both OpenAI convention and Zhipu's documented examples place `image_url` parts in `role: "user"` messages. Safe to assume; not separately quotable. |

### Extra gotcha not in the report — base64 inflation

Base64 inflates bytes by ~33%. A 5 MB image becomes ~6.7 MB of request body. If you enforce a
5 MB *raw* cap, your actual HTTP body still exceeds 5 MB — so watch the wire size, not just the
file size, on any vision path.

---

# RECOMMENDED INTEGRATION SHAPE

## Python `requests.post` for GLM-OCR — based only on VERIFIED facts

```python
import base64
import mimetypes
import requests

# ---- Configuration (all of these MUST be developer-configurable) ----
API_KEY  = "..."                                  # raw key, NO "Bearer " prefix stored here
BASE_URL = "https://open.bigmodel.cn"             # CN;  intl: "https://api.z.ai"
LAYOUT_PARSING_PATH = "/api/paas/v4/layout_parsing"
MODEL    = "glm-ocr"
AUTH_SCHEME = "Bearer "                           # see note below — the one uncertain knob

url = BASE_URL + LAYOUT_PARSING_PATH

headers = {
    "Authorization": f"{AUTH_SCHEME}{API_KEY}",   # "Bearer <key>" on both hosts (doc-verified)
    "Content-Type": "application/json",
}

# `file` must be an http(s) URL or a data:<mime>;base64,... URI. NOT a multipart upload.
mime = mimetypes.guess_type("page.png")[0] or "image/png"
with open("page.png", "rb") as fh:
    file_value = f"data:{mime};base64,{base64.b64encode(fh.read()).decode()}"

payload = {
    "model": MODEL,                   # required, enum: "glm-ocr"
    "file": file_value,               # required, URL or data URI
    "return_crop_images": False,      # optional, bool, default False
    "need_layout_visualization": False,  # optional, bool, default False
    # "start_page_id": 1,             # optional, int — PDF only
    # "end_page_id": 10,              # optional, int — PDF only
}

resp = requests.post(url, headers=headers, json=payload, timeout=300)
resp.raise_for_status()
data = resp.json()

markdown = data["md_results"]                       # a plain markdown STRING
pages    = data.get("layout_details") or []         # object[][] : pages -> elements
for page in pages:
    for el in page:
        # el["label"] in {"image","text","formula","table"}
        # el["bbox_2d"] ~ [x1,y1,x2,y2] normalized 0..1
        # el["content"]: text | image URL | table HTML
        ...
```

### Timeout advice

The vendor's own CLI uses `DEFAULT_TIMEOUT = 60` seconds, but the SDK exposes
`GLMOCR_TIMEOUT` with an example value of **600**. For large multi-page PDFs, 60s is optimistic
— use a generous timeout (≥300s) and/or chunk by `start_page_id`/`end_page_id`.

### Error handling

```python
if resp.status_code >= 400:
    body = resp.json()
    err = body.get("error") or body          # tolerate both envelopes
    code, msg = err.get("code"), err.get("message")
    # 1210 invalid param, 1211 unknown model, 1212 wrong call method,
    # 1213 missing param, 1214 invalid param
```

Retry with exponential backoff on 429 and 5xx; rate limits are undocumented (§7).

## What a developer MUST make configurable (because it could NOT be verified)

1. **The `Bearer` prefix on CN.** Documentation says `Bearer` for both hosts, but this was not
   call-verified. Store the **raw key** and build the header as `f"{AUTH_SCHEME}{API_KEY}"` so a
   bare-key CN fallback is a one-line flip. This is the highest-value knob.
2. **The page cap.** Current docs say 100 on both hosts and I found no 30-page limit, but keep
   it configurable and enforce it client-side before sending.
3. **`request_id` / `user_id`.** Reported, likely valid (platform-standard), but the parameter
   table tail was unretrievable. Do not require them; pass through only if the caller supplies them.
4. **`stream`.** No evidence it exists on this endpoint. Do not implement.
5. **`bbox_2d` scale.** Believed normalized 0..1, but not quotably documented for the HTTP API.
   Normalize empirically on first real response.
6. **Rate limits.** Completely undocumented in what I could retrieve. Must be runtime-configurable
   concurrency + backoff.
7. **Filenames/MIME.** The API takes no filename; only the `data:` URI's MIME type conveys it.
   Make MIME detection overridable — a wrong MIME on a PDF (`image/png` instead of
   `application/pdf`) is a plausible silent failure.

## Speculation (explicitly labeled — do NOT treat as fact)

- *Speculation:* the CN bare-key report may have originated from the older Zhipu
  **`/paas/v4/files/ocr`** tool endpoint or from a legacy key format, not from `layout_parsing`.
  I did not verify this.
- *Speculation:* the "intl = 30 pages" figure likely came from an **earlier doc revision** that
  has since been raised to 100. The current text on both locales says 100.
- *Speculation:* the "no `detail` field" and "≤5 MB" Zhipu vision constraints are probably
  true-by-convention (matching OpenAI-compatible behavior) rather than explicitly documented
  Zhipu limits.
