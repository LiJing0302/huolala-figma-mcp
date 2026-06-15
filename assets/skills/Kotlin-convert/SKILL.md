---
name:Kotlin-convert
description: 将设计稿/HTML 转为 Android Kotlin 原生代码的规范与检查清单。包含文件结构、样式与语义化命名、交互与循环渲染、验证项。
---

# 平台代码生成规范

将设计稿/HTML 转为 Android 原生视图时的结构、样式、交互。

## When to Use

- 将 HTML/index.html 转为 Kotlin 

## Instructions
### 布局实现
 将html的布局、属性转成安卓端对应的实现，要求保持界面高度还原
### 组件实现
1.CheckBox、RadioButton、Switch不要用image实现，需要转成系统组件实现
2.给Button、Tabbar、CheckBox、RadioButton、Switch、Slider、PickerView、InputText等添加相关事件代码
3.循环组件尽量用RecyclerView
### 图片资源处理
1.图片需要转成android的资源文件格式
2.图片资源名称进行语义化命名，持唯一性，不能和已存在的文件重名
### 字体处理
如果zip解压后有fonts目录，检测是否为安卓内置字体，没有则转成android的资源文件格式
### 样式完整性验证（⚠️ 强制要求）：
   - **必须验证**：对于每个元素，所有样式属性 = 原始行内样式的完整集合
   - **验证方法**：
     1. 提取原始行内样式的所有属性（包括 flexbox 属性：flexDirection、justifyContent、alignItems等）
     2. 转换为Android的约束和属性
     3. 确保所有属性都完整且值精确匹配
   - **验证失败处理**：必须修复后重新验证，不能跳过



