# 共炉保温编排台

本地单页应用：为 2～3 种需要在同一台炉子里分别完成连续保温的材料，
编排一条满足全部约束的**最短炉温设定曲线**；长度相同取温度序列
**字典序最小**的方案。

支持**执行记录续炉判定**：可输入 1～20 个已经执行的 5 分钟炉温档位，
逐档核验合法后，以最后已执行温度接续，在 20 档总上限内编排最短且回到
20°C 的后续曲线；首个违规档即拒绝续排。

已归档炉次还支持**电费试算**：给定开炉分钟、24 个分时电价与逐档功率，
按归档时**冻结的曲线**逐档计算 kWh 与电费（跨小时 / 跨午夜按分钟分摊），
试算只读不保存，配方之后的修改或停用均不影响结果。

- 后端：Python + FastAPI（求解核心见 `app/solver.py`，纯标准库 BFS；
  配方 / 炉次 / 归档用 SQLite 持久化，见 `app/db.py`、`app/store.py`）
- 前端：原生 HTML / CSS / JavaScript（`static/`，无任何前端构建与框架，
  页面分为「编排求解 / 材料配方 / 炉次草稿」三个标签页）

## 一条命令启动

需要 Docker（含 Compose 插件）。

```bash
docker compose up --build -d
```

启动后浏览器访问：

- 页面：<http://localhost:8000/>
- 健康检查：<http://localhost:8000/healthz>
- 接口文档（FastAPI 自带）：<http://localhost:8000/docs>

停止：

```bash
docker compose down
```

端口在 `docker-compose.yml` 的 `ports` 中修改（宿主端口在冒号左侧）。

### 不用 Docker（可选）

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 业务规则

### 材料（2～3 种）

- 保温下限 / 上限：40～180°C 的整十数，下限不高于上限；
- 连续保温时长：5、10 或 15 分钟（对应 1、2、3 个连续档位）；
- 耐受上限：不低于保温上限、至多 200°C 的整十数。

### 炉温曲线

- 炉温初态 20°C；
- 每档持续 5 分钟，设定温度为 20～200°C 的整十数；
- 首档与初态温差、相邻档温差均不超过 20°C；
- 末档必须回到 20°C；
- 所有档位温度都不得超过**任何**材料的耐受上限；
- 只有连续达到所需时长（5 分钟一档）的档位全部落在该材料的保温区间
  `[下限, 上限]` 内，该材料才算达标；
- 不同材料可以共用同一档位；材料一旦达标，后续档位对它不再有要求。

### 目标

- 总档数 ≤ 20 的前提下，求档数最少的完整曲线；
- 最短解有多条时，取温度序列字典序最小（例如先升 40°C 排在先升 60°C
  之前）；
- 有解：展示曲线图、各材料**首次达标**的连续档位区间、逐档明细表，
  以及被多种材料共用的档位；
- 无解：页面给出明确的中文原因，**不展示任何部分方案**；
- 修改任意输入后，旧结果立即清除。

### 执行记录续炉判定（可选）

- 在「已执行档位」中输入 **1～20 个**已经执行的 5 分钟炉温档位
  （20～200°C 的整十数，逗号/空格分隔）；HTTP 请求中对应
  `executedTemperatures` 字段（数组，可省略）。
- 从初态 20°C 起，按下列规则**逐档**核验已执行记录：
  - 温度必须是 20～200°C 的整十数；
  - 首档与初态、相邻档温差均不超过 20°C；
  - 每档都不得超过任何材料的耐受上限；
  - **一旦违规，立即指出首个违规档位（1-based）及原因，不给出任何续排**
    （HTTP 422，`detail` 为中文说明）。
- 合法记录逐档累计各材料的**连续**保温进度：
  - 档位落在保温区间内则进度 +1，达到所需档数即达标；
  - 档位离开区间时，**未达标者进度归零**，**已达标者保持达标**；
  - 记录中途回到 20°C 不影响合法性，后续仍可继续编排。
- 续排规则：
  - 以**最后一个已执行温度**为起点，已用档数**计入 20 档总上限**；
  - 求总档数最短、末档回到 20°C 的后续曲线；等长时取后续温度序列
    字典序最小；
  - 各材料**首次达标**区间按完整曲线（已执行 + 后续）统一编号，允许
    横跨已执行与后续档位；
  - 若已全部达标且末档已在 20°C，后续曲线为**空**；
  - 若总档数 20 以内无可行后续，返回 `solvable:false` 并明确提示，
    不展示部分曲线。

## 共享材料配方与炉次草稿（SQLite 持久化）

除了上面的即时编排，服务还支持把**材料参数保存为配方**，让多个**炉次草稿**
按顺序共用 2～3 个现有配方；核准的炉次方案可以**归档冻结**。数据保存在
SQLite（默认 `/data/planner.db`），Compose 以命名卷 `planner-data` 挂载，
容器重启后仍可读取。

### 材料配方 `/api/recipes`

- 字段与即时编排的材料**完全一致并复用同一套校验**：
  `name`（可留空，≤20 字）、`holdLow` / `holdHigh`（40～180°C 整十数，
  下限不高于上限）、`duration`（5/10/15 分钟）、`tolerance`（不低于保温
  上限、至多 200°C 的整十数）。
- 支持**创建、读取、整份修改**（PUT 为全量替换）。配方创建时版本为 1，
  每次成功修改版本 +1；**非法修改返回 422，不写入任何数据**（配方版本、
  引用草稿均保持原样）。
- 每个配方带有**状态**：`active`（可用，默认）/ `disabled`（停用）。
  新建配方与旧数据库中已有的配方一律为可用；状态保存在 SQLite 中，
  重启后保留。`GET /api/recipes` 始终列出**全部**配方并附 `status`。
- **停用 / 恢复**：`POST /api/recipes/{id}/disable`、
  `POST /api/recipes/{id}/enable`（未知配方返回 404；重复停用 / 恢复
  幂等返回 200）。状态切换**不改变材料参数、不增加配方或草稿版本、
  不重算任何炉次**；停用的配方仍可整份修改（保持停用），原有引用草稿
  照常重算与归档，已归档方案不受影响。恢复后可再次被新炉次引用。

### 炉次草稿 `/api/drafts`

- 创建时按**顺序**给出 `recipeIds`：必须是 **2～3 个互不相同的现有配方
  ID**；引用一经创建**不可更改**（没有修改引用的接口）。
- 新建炉次只能引用**可用**状态的配方：引用任一**已停用**配方 → **422**
  （`detail` 指明配方 ID），**不保存炉次**；前端下拉同样只列出可用配方，
  页面尚未刷新时由服务端拦截。停用与新建并发时按某一先后顺序串行生效：
  停用先生效，则新建失败。
- 创建即**从 20°C 空记录求解**（复用原 BFS 规则），草稿**版本从 1 开始**；
  结果（有解时的完整曲线，或无解时的中文原因）与当时的材料参数快照一同
  保存。**无解草稿同样保存**，只是不保留任何曲线。
- **修改某配方时，所有引用它的“活动”草稿在同一事务里一起重算，版本各
  +1**：有解则写入新结果，无解则**清除旧曲线并记录原因**。已归档炉次不
  再受配方修改影响。
- 炉次读取（列表 / 详情）包含：`status`（`active` / `archived`）、
  引用配方与引用时版本 `recipeVersions`、草稿 `version`、求解所用
  `materials` 参数快照、`solvable`、`result`（完整求解结果）或 `reason`
  （无解原因）。活动草稿的参数与结果一定是同一次求解写入的，**不会读到
  “新参数 + 旧结果”的混合态**。

### 归档核准方案 `POST /api/drafts/{id}/archive`

请求体 `{"version": N}` 携带**你所查看的草稿版本**：

- 版本与当前不一致（期间配方被改过）→ **409**，响应体附 `currentVersion`，
  请重新读取最新参数与结果后再归档；
- 草稿当前**无解** → **422**（中文原因），**不改变任何状态**；
- 已归档 → 409；归档与配方修改并发时，由服务端按**某一先后顺序串行生效**，
  后到的归档会收到 409，先到的归档冻结旧版本；
- 成功 → 状态变为 `archived`，**冻结当时的材料参数、草稿版本与完整求解
  结果**；此后配方再怎么改，只影响其余未归档炉次。

### 前端：切换炉次时的请求编排（响应不串用）

「炉次草稿」详情区对查看 / 刷新 / 归档三类请求做了严格编排，避免慢响应
串用（接口字段、状态码与冻结规则均不变，全部为前端行为）：

- **只认当前选择的最新请求**：每次「查看」或「刷新」都生成新一代请求，
  详情、曲线、提示与归档按钮只接受最新一代的响应。先看甲再看乙时，晚
  返回的甲（无论成功、404/500 等失败还是网络异常）一律作废，**不会覆盖
  乙的详情或提示**。
- **等待期间仍可自由切换炉次**（包括“在甲等归档时切到乙、再切回甲”），
  也可再次点刷新（旧请求自动作废）。
- **查看或刷新一发起，旧详情立即失去归档资格**：在目标详情**成功读回
  之前**，归档按钮始终禁用（显示“详情加载中…”）；读取失败或网络异常时
  保持禁用并提示重试，杜绝把归档发到一份已经过期的详情上。
- **归档绑定点击那一刻的炉次 ID 与 `version`**：提交后即使立刻切到别的
  炉次，该归档请求仍照常发往服务端、照常生效；但它的成功 / 409 / 422 /
  网络异常**不会改写新炉次的详情、曲线、提示或按钮**（仅在成功时后台静默
  刷新列表状态）。新炉次读回后，完全按其自身状态（活动 / 已归档、版本）
  决定按钮。
- **切走再回到同一炉次**：回到甲（或对甲再次「刷新」）会生成新一代详情
  请求；此前那笔归档**晚到的回包对甲同样作废**——既不会清空 / 覆盖新读回
  的详情与曲线，也不会插入旧的成功或 409/422 提示，更不会代替用户再触发
  一次详情 GET。它只释放在途状态、按当前有效详情恢复归档按钮。若旧归档
  已成功，列表状态在后台静默同步；甲的最新状态以新 GET 读回的内容为准。
- **留在原炉次、期间没有重新查看或刷新**：归档成功显示冻结方案与成功
  提示，按钮转为“已归档”；409（版本过期 / 已归档）或 422（当前无解）
  都会**重新读取同一炉次**，并把中文原因**保留在页面上**（409 同时提示
  当前版本号）；网络失败不改详情，提示可重试。
- **同一炉次归档请求未结束前不得重复提交**（归档中按钮禁用并按炉次 ID
  去重，切走再回来也不解锁）；不同炉次的归档互不影响。归档按钮始终只按
  **当前有效详情**恢复：详情加载中、读取失败（含网络异常）或已归档时
  一律禁用。

## 求解算法

在档位最多 20、温度只有 19 个整十值的规模下，直接做广度优先搜索：

- 状态 = `(当前温度, 各材料连续保温进度)`；进度为“当前已连续处于其区间
  内的档数”，达标后记为完成态；
- 从零编排：从初态 `(20, 全 0)` 出发；带执行记录时：先逐档核验并重放
  记录得到 `(最后已执行温度, 当前进度)`，再以该状态为起点；
- 按温度**升序**扩展下一档（温差 ≤ 20、不超过耐受上限）。BFS 保证
  档数最少，同层按温度升序入队保证温度序列字典序最小；
- 目标状态：当前温度回到 20°C 且所有材料均已完成；
- 扩展深度（已执行档数 + 后续档数）超过 20 即停止；搜不到目标即为无解。
- 另含一个保守的无解预检（如保温下限高于所有耐受上限的最小值），
  仅在无执行记录时使用，用于给出更具体的原因；预检通过不代表必然有解，
  最终以 BFS 为准。

## API

`POST /api/schedule`

请求体字段：

- `materials`（必填，2～3 项）：每种材料的名称与温度参数；
- `executedTemperatures`（可选）：1～20 个已执行档位温度的整数数组；
  省略或传 `[]` 表示从零编排。

其余接口（配方与炉次管理，均返回 JSON）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/recipes` | 列出全部配方（含 `status`：`active` / `disabled`） |
| POST | `/api/recipes` | 创建配方（201，版本从 1 开始，默认可用） |
| GET | `/api/recipes/{id}` | 读取单个配方（含状态） |
| PUT | `/api/recipes/{id}` | 整份修改配方；原子重算引用它的活动草稿（版本 +1）；停用配方也可修改并保持停用 |
| POST | `/api/recipes/{id}/disable` | 停用配方（200；未知 404；不改参数/版本，不重算草稿） |
| POST | `/api/recipes/{id}/enable` | 恢复配方为可用（200；未知 404） |
| GET | `/api/drafts` | 列出全部炉次（含状态/参数/版本/结果或无解原因） |
| POST | `/api/drafts` | 按 2～3 个不同现有配方 ID 创建炉次并从空记录求解（201；引用已停用配方 422） |
| GET | `/api/drafts/{id}` | 读取炉次详情（归档后返回冻结快照） |
| POST | `/api/drafts/{id}/archive` | 携带查看版本归档（过期 409 / 无解 422） |
| POST | `/api/drafts/{id}/tariff-trial` | 已归档炉次按冻结曲线试算电费（未知 404 / 未归档或参数非法 422；只读不保存） |

### 从零编排（可直接复制执行）

```bash
curl -sS -X POST http://localhost:8000/api/schedule \
  -H 'Content-Type: application/json' \
  -d '{
    "materials": [
      {"name": "材料A", "holdLow": 60, "holdHigh": 100, "duration": 10, "tolerance": 150},
      {"name": "材料B", "holdLow": 80, "holdHigh": 120, "duration": 5,  "tolerance": 160}
    ]
  }'
```

返回（HTTP 200，节选）：

```json
{
  "solvable": true,
  "hasExecuted": false,
  "temperatures": [40, 60, 80, 60, 40, 20],
  "executedTemperatures": [],
  "continuationTemperatures": [40, 60, 80, 60, 40, 20],
  "executedCount": 0,
  "continuationCount": 6,
  "stepCount": 6,
  "totalMinutes": 30,
  "alreadyComplete": false,
  "toleranceCap": 150,
  "windows": [
    {"material": "材料A", "startStep": 2, "endStep": 3, "minutes": 10},
    {"material": "材料B", "startStep": 3, "endStep": 3, "minutes": 5}
  ]
}
```

### 带执行记录续炉（可直接复制执行）

已执行 `[40, 60, 80]` 三档：材料 A 已连续保温 2 档（区间 60～100），
材料 B 已保温 1 档（区间 80～120）。续排只需降温回 20°C：

```bash
curl -sS -X POST http://localhost:8000/api/schedule \
  -H 'Content-Type: application/json' \
  -d '{
    "materials": [
      {"name": "材料A", "holdLow": 60, "holdHigh": 100, "duration": 10, "tolerance": 150},
      {"name": "材料B", "holdLow": 80, "holdHigh": 120, "duration": 5,  "tolerance": 160}
    ],
    "executedTemperatures": [40, 60, 80]
  }'
```

返回（HTTP 200，节选）：

```json
{
  "solvable": true,
  "hasExecuted": true,
  "temperatures": [40, 60, 80, 60, 40, 20],
  "executedTemperatures": [40, 60, 80],
  "continuationTemperatures": [60, 40, 20],
  "executedCount": 3,
  "continuationCount": 3,
  "stepCount": 6,
  "totalMinutes": 30,
  "alreadyComplete": false,
  "steps": [
    {"index": 1, "temperature": 40, "deltaFromPrev": 20, "executed": true,  "phase": "executed"},
    {"index": 4, "temperature": 60, "deltaFromPrev": -20, "executed": false, "phase": "continuation"}
  ]
}
```

字段说明（续炉相关）：

| 字段 | 含义 |
| --- | --- |
| `hasExecuted` | 是否带已执行记录 |
| `executedTemperatures` / `executedCount` | 已执行档位温度与档数 |
| `continuationTemperatures` / `continuationCount` | 后续曲线温度与档数（可为空数组） |
| `alreadyComplete` | 已执行记录结束时是否已全部达标且回到 20°C（此时后续为空） |
| `steps[].executed` / `steps[].phase` | 每档属于 `executed`（已执行）还是 `continuation`（后续） |
| `windows` | 各材料首次达标区间，按**完整曲线**统一编号（允许横跨两段） |

### 已全部达标且回到 20°C —— 后续为空

```bash
curl -sS -X POST http://localhost:8000/api/schedule \
  -H 'Content-Type: application/json' \
  -d '{
    "materials": [
      {"name": "材料A", "holdLow": 60, "holdHigh": 100, "duration": 10, "tolerance": 150},
      {"name": "材料B", "holdLow": 80, "holdHigh": 120, "duration": 5,  "tolerance": 160}
    ],
    "executedTemperatures": [40, 60, 80, 100, 100, 120, 100, 80, 60, 40, 20]
  }'
```

返回（节选）：`"solvable": true, "alreadyComplete": true,
"continuationTemperatures": [], "continuationCount": 0`。

### 执行记录违规 —— HTTP 422，指出首个违规档

第 2 档由 40°C 跳到 80°C（温差 40°C > 20°C）：

```bash
curl -sS -X POST http://localhost:8000/api/schedule \
  -H 'Content-Type: application/json' \
  -d '{
    "materials": [
      {"name": "材料A", "holdLow": 60, "holdHigh": 100, "duration": 10, "tolerance": 150},
      {"name": "材料B", "holdLow": 80, "holdHigh": 120, "duration": 5,  "tolerance": 160}
    ],
    "executedTemperatures": [40, 80]
  }'
```

```json
{"detail": "已执行记录第 2 档温度 80°C 与上一档 40°C 温差 40°C，超过 20°C 上限。"}
```

超过耐受上限（所有材料耐受上限最小值为 150°C，第 7 档 160°C 违规）：

```bash
curl -sS -X POST http://localhost:8000/api/schedule \
  -H 'Content-Type: application/json' \
  -d '{
    "materials": [
      {"name": "材料A", "holdLow": 60, "holdHigh": 100, "duration": 10, "tolerance": 150},
      {"name": "材料B", "holdLow": 80, "holdHigh": 120, "duration": 5,  "tolerance": 160}
    ],
    "executedTemperatures": [40, 60, 80, 100, 120, 140, 160]
  }'
# {"detail":"已执行记录第 7 档温度 160°C 超过所有材料耐受上限的最小值 150°C。"}
```

### 无可行后续 —— HTTP 200，solvable=false

已执行档数 + 最短必要后续超过 20 档时（HTTP 200，便于页面区分“无解”与
“参数错误”）：

```json
{"solvable": false, "reason": "已执行 20 档后，在 20 档总上限内找不到满足剩余材料并回到 20°C 的后续曲线，无法续排。"}
```

参数非法（材料参数错误、已执行记录为空/超过 20 个/非整十数/越界等）
时返回 HTTP 422，`detail` 为中文错误说明。响应中**不会**附带任何部分
曲线。

### 配方与炉次草稿（可直接复制执行）

```bash
# 1) 创建两个材料配方（版本均从 1 开始，默认可用）
curl -sS -X POST http://localhost:8000/api/recipes \
  -H 'Content-Type: application/json' \
  -d '{"name":"钢甲","holdLow":60,"holdHigh":100,"duration":10,"tolerance":150}'
# {"id":1,"name":"钢甲","holdLow":60,...,"status":"active","version":1,"createdAt":"...","updatedAt":"..."}

curl -sS -X POST http://localhost:8000/api/recipes \
  -H 'Content-Type: application/json' \
  -d '{"name":"铜乙","holdLow":80,"holdHigh":120,"duration":5,"tolerance":160}'

# 2) 创建炉次草稿：按顺序引用 2 个不同现有配方，从 20°C 空记录求解
curl -sS -X POST http://localhost:8000/api/drafts \
  -H 'Content-Type: application/json' \
  -d '{"name":"十月首炉","recipeIds":[1,2]}'
```

返回（HTTP 201，节选）：

```json
{
  "id": 1,
  "name": "十月首炉",
  "status": "active",
  "recipeIds": [1, 2],
  "recipeVersions": {"1": 1, "2": 1},
  "version": 1,
  "materials": [
    {"name": "钢甲", "holdLow": 60, "holdHigh": 100, "duration": 10, "tolerance": 150},
    {"name": "铜乙", "holdLow": 80, "holdHigh": 120, "duration": 5,  "tolerance": 160}
  ],
  "solvable": true,
  "result": { "solvable": true, "temperatures": [40, 60, 80, 60, 40, 20],
              "stepCount": 6, "totalMinutes": 30, "steps": [ ... ],
              "windows": [ ... ], "sharedSteps": [ ... ], "materials": [ ... ] },
  "reason": null,
  "createdAt": "...", "updatedAt": "...", "archivedAt": null
}
```

### 修改配方 → 引用草稿一起重算（版本 +1）

```bash
curl -sS -X PUT http://localhost:8000/api/recipes/1 \
  -H 'Content-Type: application/json' \
  -d '{"name":"钢甲","holdLow":70,"holdHigh":100,"duration":10,"tolerance":150}'
```

```json
{
  "recipe": { "id": 1, "holdLow": 70, "version": 2, "...": "..." },
  "recomputedDrafts": [
    { "id": 1, "status": "active", "version": 2, "solvable": true,
      "materials": [ { "holdLow": 70, "...": "..." } ],
      "result": { "...": "与 materials 同版的完整结果" } }
  ]
}
```

非法修改（如保温下限高于上限、耐受上限低于保温上限、非整十数等）返回
**422 且不改变任何数据**：配方版本不增加，引用草稿也不会被重算。
新参数导致草稿无解时，草稿仍保存：`version` 增加、`solvable:false`、
`result:null`、`reason` 为中文原因。

### 停用配方 → 拒绝引用 → 恢复

```bash
# 停用配方 1：只切换状态，材料参数、配方/草稿版本不变，不重算任何炉次
curl -sS -X POST http://localhost:8000/api/recipes/1/disable
# {"id":1,"name":"钢甲",...,"status":"disabled","version":2,...}

# 停用期间新建炉次引用它 → 422，指明配方 ID，不保存炉次
curl -sS -X POST http://localhost:8000/api/drafts \
  -H 'Content-Type: application/json' \
  -d '{"name":"十月二炉","recipeIds":[1,2]}'
# 422：{"detail":"配方 ID 1 已停用，不能用于新建炉次。"}

# GET /api/recipes 仍列出全部配方并附状态
curl -sS http://localhost:8000/api/recipes
# [{"id":1,...,"status":"disabled",...},{"id":2,...,"status":"active",...}]

# 恢复为可用，之后可再次被新炉次引用
curl -sS -X POST http://localhost:8000/api/recipes/1/enable
# {"id":1,"name":"钢甲",...,"status":"active","version":2,...}

# 未知配方的状态操作 → 404
curl -sS -X POST http://localhost:8000/api/recipes/999/disable
# 404：{"detail":"配方 999 不存在。"}
```

停用不改变已有炉次：引用它的活动草稿在配方修改时照常重算、可正常归档，
已归档方案保持冻结；停用的配方本身也仍可整份修改（PUT）并保持停用。

### 归档：携带所查看的版本

```bash
# 正常归档（当前查看的就是 v2）
curl -sS -X POST http://localhost:8000/api/drafts/1/archive \
  -H 'Content-Type: application/json' -d '{"version":2}'
# 200，节选：
# {"id":1,"status":"archived","version":2,
#  "materials":[...冻结快照...],"result":{...冻结完整结果...},
#  "archivedAt":"2026-10-01T08:00:00Z", ...}

# 期间配方被改过（草稿已到 v3），仍带 v2 归档 → 409
curl -sS -X POST http://localhost:8000/api/drafts/1/archive \
  -H 'Content-Type: application/json' -d '{"version":2}'
# 409：{"detail":{"detail":"炉次草稿已过期：你查看的是版本 2，当前为版本 3，请重新读取后再归档。",
#                 "currentVersion":3}}

# 当前无解时归档 → 422，状态不变
# 422：{"detail":"材料「钢甲」的保温下限 170°C 已高于所有材料耐受上限的最小值 160°C，..."}
```

归档成功后再次 `PUT /api/recipes/1` 只影响其他**未归档**炉次；
`GET /api/drafts/1` 永远返回归档时冻结的版本、参数与结果。

### 已归档炉次电费试算 `POST /api/drafts/{id}/tariff-trial`

只对**已归档**炉次开放，且只读取归档时**冻结的曲线**：之后配方被修改或
停用、草稿版本如何变化，试算使用的温度序列都不变。**试算不保存、不改动
任何方案**。请求体：

- `startMinute`：开炉分钟，从当天 00:00 起算的 **0～1439 整数**；
- `prices`：按 **00～23 时**排列的 **24 个**电价（元/kWh），非负有限数，
  电价**每天重复**（跨午夜的档位取次日 00 时起的电价）；
- `powers`：与**冻结曲线等长**的逐档功率（kW），非负有限数，每档功率在
  其 **5 分钟**内恒定。

计算规则：每档 `kWh = 功率 × 5/60`；档位跨小时（含跨午夜）时，按落入各
小时的分钟数分摊电费。**逐档金额各自四舍五入到两位**（元）；**总费用先
汇总未舍入的逐档金额，再四舍五入到两位**，因此逐档金额之和可能与总费用
相差 1 分；`kWh` 不做业务舍入。状态码：未知炉次 **404**；炉次存在但**未
归档**或任一参数非法 **422**（中文 `detail`）。

沿用上文归档好的炉次 #1（冻结曲线 `[40,60,80,60,40,20]`，共 6 档）。

```bash
# 08:00 开炉（480 分钟），全天电价 0.6 元/kWh；功率 60/120/0/60/60/120 kW
curl -sS -X POST http://localhost:8000/api/drafts/1/tariff-trial \
  -H 'Content-Type: application/json' \
  -d '{
    "startMinute": 480,
    "prices": [0.6,0.6,0.6,0.6,0.6,0.6,0.6,0.6,0.6,0.6,0.6,0.6,
               0.6,0.6,0.6,0.6,0.6,0.6,0.6,0.6,0.6,0.6,0.6,0.6],
    "powers": [60,120,0,60,60,120]
  }'
```

返回（HTTP 200）：

```json
{
  "draftId": 1,
  "startMinute": 480,
  "stepCount": 6,
  "steps": [
    {"index": 1, "temperature": 40, "minutes": 5, "startMinute": 480, "kwh": 5.0,  "cost": 3.0},
    {"index": 2, "temperature": 60, "minutes": 5, "startMinute": 485, "kwh": 10.0, "cost": 6.0},
    {"index": 3, "temperature": 80, "minutes": 5, "startMinute": 490, "kwh": 0.0,  "cost": 0.0},
    {"index": 4, "temperature": 60, "minutes": 5, "startMinute": 495, "kwh": 5.0,  "cost": 3.0},
    {"index": 5, "temperature": 40, "minutes": 5, "startMinute": 500, "kwh": 5.0,  "cost": 3.0},
    {"index": 6, "temperature": 20, "minutes": 5, "startMinute": 505, "kwh": 10.0, "cost": 6.0}
  ],
  "totalKwh": 35.0,
  "totalCost": 21.0
}
```

跨小时分摊示例（07:58 开炉，07 时电价 0.4、08 时 1.2，其余 0.4；首档
60 kW 落在 07:58～08:00 的 2 分钟按 0.4、落在 08:00～08:03 的 3 分钟按
1.2 计费，电费 = 60×2/60×0.4 + 60×3/60×1.2 = 0.8 + 3.6 = 4.4 元）：

```bash
curl -sS -X POST http://localhost:8000/api/drafts/1/tariff-trial \
  -H 'Content-Type: application/json' \
  -d '{
    "startMinute": 478,
    "prices": [0.4,0.4,0.4,0.4,0.4,0.4,0.4,0.4,1.2,0.4,0.4,0.4,
               0.4,0.4,0.4,0.4,0.4,0.4,0.4,0.4,0.4,0.4,0.4,0.4],
    "powers": [60,120,0,60,60,120]
  }'
# 节选：steps[0] = {"index":1,"startMinute":478,"kwh":5.0,"cost":4.4,...}
#       "totalKwh": 35.0, "totalCost": 40.4
```

跨午夜示例（23:58 = 1438 分钟开炉，23 时电价 0.8、00 时起 0.3，6 档全为
120 kW；首档 23:58～00:03 按 2 分钟 0.8 + 3 分钟 0.3 分摊，次日各档的
`startMinute` 对 1440 取模）：

```bash
curl -sS -X POST http://localhost:8000/api/drafts/1/tariff-trial \
  -H 'Content-Type: application/json' \
  -d '{
    "startMinute": 1438,
    "prices": [0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,
               0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.8],
    "powers": [120,120,120,120,120,120]
  }'
# 节选：各档 startMinute = [1438,3,8,13,18,23]；首档 cost 5.0，
#       其余各档 3.0；"totalKwh": 60.0, "totalCost": 20.0
```

逐档金额四舍五入、总费用汇总未舍入值的示例（各档 1 kW、电价 0.3：单档
电费 0.025 元，逐档显示 `0.03`，6 档合计按未舍入值汇总为 6×0.025 = `0.15`，
而不是 6×0.03 = 0.18）：

```bash
curl -sS -X POST http://localhost:8000/api/drafts/1/tariff-trial \
  -H 'Content-Type: application/json' \
  -d '{"startMinute":0,"prices":[0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3],"powers":[1,1,1,1,1,1]}'
# 各档 "cost": 0.03；"totalCost": 0.15
```

错误情况：

```bash
# 未归档炉次
curl -sS -X POST http://localhost:8000/api/drafts/2/tariff-trial \
  -H 'Content-Type: application/json' \
  -d '{"startMinute":0,"prices":[0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3,0.3],"powers":[1,1,1,1,1,1]}'
# 422：{"detail":"炉次 2 尚未归档，不能试算电费。"}
# 未知炉次 -> 404：{"detail":"炉次 99 不存在。"}
# 功率档数不符 -> 422：{"detail":"功率档数必须与冻结曲线等长（6 档），当前为 5 档。"}
# 电价数量不符 -> 422：{"detail":"电价必须恰好为 24 个（按 00～23 时排列），当前为 23 个。"}
# 开炉分钟越界 -> 422：{"detail":"开炉分钟必须是 0～1439 的整数。"}
```

前端「炉次草稿」详情对已归档炉次提供试算卡片：**切换炉次、刷新详情或
编辑任一试算输入时旧试算立即清除**；此前请求的迟到响应（成功 / 404 /
422 / 网络异常）按请求代际一律作废，不会回填到当前视图。

## 目录结构

```
.
├── app/
│   ├── __init__.py
│   ├── main.py        # FastAPI 路由与参数校验（schedule / recipes / drafts / archive / 电费试算）
│   ├── solver.py      # 规则常量、校验与 BFS 求解（配方与草稿复用）
│   ├── tariff.py      # 已归档冻结曲线的电费试算纯计算（Decimal，跨小时 / 跨午夜分摊）
│   ├── db.py          # SQLite 连接、建表与全局串行锁
│   └── store.py       # 配方 / 炉次草稿 / 归档的事务化读写
├── static/
│   ├── index.html     # 页面（编排求解 / 材料配方 / 炉次草稿 三个标签页）
│   ├── styles.css     # 样式
│   └── app.js         # 表单、请求、结果与 SVG 曲线渲染
├── Dockerfile
├── docker-compose.yml # 含命名卷 planner-data → /data，持久化 planner.db
├── requirements.txt
└── README.md
```

数据库路径：环境变量 `PLANNER_DB`（Compose 中为 `/data/planner.db`）；
裸跑且 `/data` 不可写时自动落到仓库内 `data/planner.db`。
