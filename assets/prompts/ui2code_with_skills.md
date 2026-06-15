Figma UI to Code
输入参数：
    Figma URL: 必填，没有则报错
    目标语言: 默认Html
    图片倍数: 可选，默认3倍
    转码要求：可选

创建tolo list：
#步骤 1：获取 ZIP 包数据
执行：
调用 MCP 工具 figma_to_code_package，
验证返回结果包含 zip_url 和 metadata.name
重试：第一次失败等待2-3秒后重试一次，两次都失败则提示用户检测是否有figma访问权限
成功输出：
✅ DSL数据获取成功：- zip_url: <zip包下载地址>- metadata.name: <设计稿名称>

#步骤 2：下载和解压 ZIP 包
下载：
文件命名规则（强制）：
使用系统命令检测是否存在同名ZIP包 {metadata.name}.zip（如 test -f {metadata.name}.zip 或 ls {metadata.name}.zip）
如果不存在 {metadata.name}.zip，使用 {metadata.name}.zip 作为文件名
如果存在 {metadata.name}.zip，检查 {metadata.name}_1.zip、{metadata.name}_2.zip 等，找到最大数字 N，使用 {metadata.name}_<N+1>.zip 作为文件名
例如：如果存在 {metadata.name}.zip 和 {metadata.name}_1.zip，则使用 {metadata.name}_2.zip
必须执行此检查步骤，不能直接覆盖现有文件
位置：当前工作目录
解压：
使用 unzip {zip文件名}解压，解压文件夹名保持和ZIP包同名
验证：确认存在 index.html 文件
失败：输出错误信息，立即停止

#步骤3:循环组件调整
检测zip解压后是否有vlm_result.json,如果不存在，则采用独立的agent执行图片分析：
自动读取图片文件 design.png到多模态大模型
文本提示词：识别UI结构 ,输出前端可用json结构,要求包含x,y,width,height,type,text(如有),children(如有)字段
输出文件名：vlm_result.json


循环组件层级调用MCP 协议读取 skills://adjust-list-group），执行该步骤时不要看步骤4


#步骤4：读取 index.html 并转换代码
默认加载MCP Resource提供的转码风格和特点，用户也可指定自己的转码风格或特点
 react、vue、H5、Web加载 skills://react-vue-H5-convert
 React Native加载skills://ReactNative-convert
 ObjectiveC加载skills://ObjectiveC-convert
 Kotlin加载skills://Kotlin-convert

#步骤5: 其他转码要求
执行用户指定的要求，修改位置或其他逻辑，并适配工程

#步骤6：输出结果
输出格式：
加载的skills
✅ 代码生成成功！📁 目标代码目录：生成代码位于 {3.0步骤生成的目录}📋 详细列表：1. 代码文件：{列出所有文件}2. 验证结果：全部通过3. 文件结构：   {3.0步骤生成的目录}/   └── {主要代码文件}

