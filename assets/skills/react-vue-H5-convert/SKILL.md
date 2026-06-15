---
name: react-vue-H5-convert
description: 将设计稿转换后的 index.html 文件转换为目标平台代码（H5/React/Vue），包括样式抽离、语义化命名、交互实现和循环渲染支持。
---

# U2C 代码转换

将 UI2Code 工具生成的 index.html 转换为规范的前端代码，支持 H5、React、Vue 平台。

## When to Use

- 当需要将设计稿转换后的 index.html 转换为目标平台代码时
- 当需要进行样式抽离和语义化 class 命名时
- 当需要识别并实现交互组件（选中态、按钮等）时
- 当需要实现循环渲染（React/Vue 平台）时

## Instructions

### 参数说明

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `source_dir` | string | - | ZIP 包解压后的目录路径 |
| `target_dir` | string | `${source_dir}/target_code` | 代码输出目录 |
| `platform` | string | `H5` | 目标平台：H5、React、Vue |

### 步骤 0：创建代码文件夹

- 如果用户指定了代码保存位置，则以用户指定的位置创建代码文件夹
- 否则在 `${source_dir}` 中创建子文件夹 `target_code` 存储代码

### 步骤 1：读取 index.html 并分析结构

1. **完整读取**：读取 `${source_dir}/index.html` 文件

2. **结构分析**：
   - 记录每个元素的层级关系（父子关系）
   - 记录同级元素的顺序
   - 记录每个元素的类型（div、span、img 等）
   - 记录每个元素的行内样式和属性

3. **样式提取**：提取所有行内样式属性，包括：
   - 尺寸：width、height
   - 间距：margin、padding、margin-top、margin-left 等
   - 定位：position、top、left、right、bottom
   - 字体：font-family、font-size、font-weight、line-height
   - 颜色：color、background-color、border-color
   - 边框：border、border-radius、border-width 等
   - 布局：display、flex-direction、justify-content、align-items 等

4. **图片路径提取**：提取所有 `<img src>` 和 `background-image` 路径

5. **文本内容提取**：提取所有文本内容，特别注意需要精确宽度的文本元素

### 步骤 2：处理资源（图片和字体）

#### 2.1 判断资源目录

- 检查 `${source_dir}` 下是否包含 `images/` 目录（图片资源）
- 检查 `${source_dir}` 下是否包含 `fonts/` 目录（字体资源）
- 如果包含则执行后续流程，如果不包含则跳过对应步骤

#### 2.2 图片语义化命名规则

> ⚠️ **强制要求**

| 优先级 | 命名来源 |
|--------|----------|
| 1 | 附近文本内容 |
| 2 | 用途功能 |
| 3 | 位置作用 |

**命名格式**：
- 使用小写字母、数字、连字符（-）
- 多个单词用连字符连接
- 示例：`favorite-driver-icon.png`、`back-arrow-icon.png`、`user-avatar.png`

**禁止**：使用 UUID、随机字符串、`image_{序号}` 或中文命名

#### 2.3 复制资源

| 资源类型 | 源目录 | 目标目录 | 命名规则 |
|----------|--------|----------|----------|
| 图片 | `${source_dir}/images/` | `${target_dir}/images/` | 语义化命名 |
| 字体 | `${source_dir}/fonts/` | `${target_dir}/fonts/` | 保持原有文件名 |

> ⚠️ **强制要求**：更新所有代码文件中的路径引用

### 步骤 3：代码文件结构生成

**默认文件结构**：

| 平台 | 文件结构 |
|------|----------|
| H5 | `index.html`、`styles.css`、`script.js` |
| React | `index.jsx`、`styles.css` |
| Vue | `index.vue` |

如果用户指定了文件结构，以用户要求为准。

### 步骤 4：样式抽离和语义化 class 命名

#### 4.1 语义化 class 命名

| 组件类型 | 命名规则 | 示例 |
|----------|----------|------|
| 文本组件 | 根据文本内容 | `nav-title`、`driver-name` |
| 容器组件 | 根据功能 | `nav-bar`、`driver-card` |
| 图片组件 | 根据用途 | `back-icon`、`driver-avatar` |

**禁止**：`container-{ID}` 或 `comp-{ID}` 格式

#### 4.2 提取公共样式

1. 找出相同语义化名称的组件
2. 分类：
   - 公共样式：字体、颜色、边框（非位置相关）
   - 单独样式：布局、尺寸、间距、定位
3. 多 class 组合：`class="driver-name driver-name-common"`

#### 4.3 精确样式匹配

> ⚠️ **强制要求**

| 属性类型 | 要求 |
|----------|------|
| 数值属性 | width、height、margin、padding、font-size、line-height 等必须精确匹配原始值（包括小数） |
| 定位属性 | position、top、left、right、bottom 必须精确匹配 |
| 颜色值 | rgba 颜色值必须完全一致 |

#### 4.4 样式完整性验证

> ⚠️ **强制要求**：公共样式 + 单独样式 = 原始行内样式的完整集合

**常见遗漏属性**：flex-direction、justify-content、align-items、align-self、flex-wrap、column-gap 等 flexbox 属性

### 步骤 5：识别交互组件并实现状态切换

#### 5.1 选中态组件识别

- 查找相同结构的容器（Tab 项、筛选选项）
- 检查样式差异：背景色、边框、文本颜色
- 添加状态 class：`filter-tab-active`、`filter-tab-inactive`

#### 5.2 样式分类规则

| 样式类型 | 位置 class | 状态 class |
|----------|------------|------------|
| 圆角位置 | ✓ | - |
| 布局/尺寸/间距/定位 | ✓ | - |
| 默认边框 | ✓ | - |
| 选中态背景色 | - | ✓ |
| 选中态边框处理 | - | ✓ |
| 文本颜色变化 | - | ✓ |

#### 5.3 边框处理规则

| 场景 | 位置 class | 状态 class |
|------|------------|------------|
| 未选中有边框，选中无边框 | 设置默认边框 | `border: none` |
| 未选中无边框，选中有边框 | 不设置边框 | 添加边框 |
| 边框颜色不同 | 设置默认颜色 | 覆盖边框颜色 |

#### 5.4 交互逻辑实现

| 平台 | 实现方式 |
|------|----------|
| H5 | `addEventListener` + `classList.add/remove` |
| React | `onClick` + 组件状态管理 |
| Vue | `@click` + `methods` |

### 步骤 6：循环渲染支持

#### 6.1 H5 平台

> ⚠️ **不支持循环渲染**

- 禁止使用 `document.createElement()` 或 `innerHTML` 创建 DOM 元素
- 所有重复结构必须在 HTML 中完整写出

#### 6.2 React 平台

**循环组件识别条件**（必须全部满足）：
- 组件结构完全相同：类型、数量、层级完全一致
- 样式基本相同：公共样式相同，单独样式差异 ≤ 3 个属性
- 在 HTML 中连续出现

**实现方式**：
```jsx
{items.map((item, index) => (
  <div key={index} className="item">
    <img src={item.icon} alt={item.name} />
    <span>{item.name}</span>
  </div>
))}
```

> ⚠️ **强制要求**：必须为每个循环项添加 `key` 属性

#### 6.3 Vue 平台

**实现方式**：
```vue
<div v-for="(item, index) in items" :key="index" class="item">
  <img :src="item.icon" :alt="item.name" />
  <span>{{ item.name }}</span>
</div>
```

> ⚠️ **强制要求**：必须为每个循环项添加 `:key` 属性

### 步骤 7：验证

#### 7.1 验证项

| 验证项 | 说明 |
|--------|------|
| 结构一致性 | HTML 结构必须与原始 index.html 完全一致 |
| 语义化命名 | class 和图片名称都是语义化的 |
| 样式完整性 | 所有行内样式已抽离，公共+单独样式组合正确 |
| 资源完整性 | 图片/字体路径正确，文件存在 |
| 交互功能 | 识别了选中态组件和按钮，添加了交互样式和逻辑 |
| 循环渲染 | React/Vue 平台正确使用循环渲染（H5 忽略） |

#### 7.2 验证输出格式

```
✅ 代码转换验证：
- 结构一致性：通过/失败
- 语义化命名：通过/失败
- 样式完整性：通过/失败
- 资源完整性：通过/失败
- 交互功能：通过/失败
- 循环渲染：通过/失败（H5 平台忽略）
- 验证结果：通过/失败
- 问题列表：[如果有问题，列出所有问题]
```

#### 7.3 验证失败处理

1. 识别问题：明确哪个验证项失败
2. 分析原因：为什么会出现
3. 修复问题：根据具体问题修复
4. 重新验证：修复后完整验证
5. 确认通过：所有验证项通过后才能继续
