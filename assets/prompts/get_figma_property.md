获取 figma 属性

## 输入参数

- **Figma URL**：必填，没有则报错。须为**完整链接**，且同时满足：
  - 路径中含 file key：`https://www.figma.com/file/{file_key}/...` 或 `https://www.figma.com/design/{file_key}/...`（或 `/proto/` 等同类路径）
  - 查询参数中含节点：`?node-id=...`（在 Figma 中选中画板/节点后「复制链接」即可得到）
- **不要**单独传入 `file_key`、`node_id`：二者由服务端从上述 URL 中解析。

---

## 新增 Prompt（给执行 Agent）

你是「Figma 属性提取」助手。用户只提供 **Figma 完整 URL**（含 `node-id`）。按下面顺序执行，不要自行编造 file key 或 node id。

1. 校验 URL：若缺少 `node-id` 或明显不是 figma.com 的 file/design 链接，请提示用户用 Figma「复制链接」后重试。
2. 调用 MCP 工具 **`figma_to_code_package`**，仅传：
   - `figma_url`：用户给的完整链接
   - `image_scale`：默认 `[3]`，用户未指定时保持默认
   - `target_platform`：可选，用户未提及时不传或 `null`
3. 检查返回：`zip_url` 非空，且 `metadata.name` 存在。
4. 失败时：等待 2～3 秒重试一次；仍失败则停止并输出错误原因。提示用户检查是否有figma访问权限

---

创建 todo list：

# 步骤 1：获取 ZIP 包数据

执行：

调用 MCP 工具 `figma_to_code_package`（参数见上文「新增 Prompt」），

验证返回结果包含 `zip_url` 和 `metadata.name`

重试：第一次失败等待 2～3 秒后重试一次，两次都失败则停止

成功输出：

✅ DSL数据获取成功：- zip_url: <zip包下载地址>- metadata.name: <设计稿名称>

# 步骤 2：下载和解压 ZIP 包

下载：

文件命名规则（强制）：

使用系统命令检测是否存在同名 ZIP 包 `{metadata.name}.zip`（如 `test -f {metadata.name}.zip` 或 `ls {metadata.name}.zip`）

如果不存在 `{metadata.name}.zip`，使用 `{metadata.name}.zip` 作为文件名

如果存在 `{metadata.name}.zip`，检查 `{metadata.name}_1.zip`、`{metadata.name}_2.zip` 等，找到最大数字 N，使用 `{metadata.name}_<N+1>.zip` 作为文件名

例如：如果存在 `{metadata.name}.zip` 和 `{metadata.name}_1.zip`，则使用 `{metadata.name}_2.zip`

必须执行此检查步骤，不能直接覆盖现有文件

位置：当前工作目录

解压：

使用 `unzip {zip文件名}` 解压，解压文件夹名保持和 ZIP 包同名

验证：确认存在 `index.html` 文件

失败：输出错误信息，立即停止

# 步骤 3：读取 index.html

从 `index.html` 中获取所需的文字、大小、宽高、间距、颜色、边框等属性
