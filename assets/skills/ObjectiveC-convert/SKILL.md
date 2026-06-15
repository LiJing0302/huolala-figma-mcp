---
name:ObjectiveC-convert
description: 将设计稿/HTML 转为 iOS Objective-C原生代码的规范与检查清单。包含文件结构、样式与语义化命名、交互与循环渲染、验证项。
---

# iOS 平台代码生成规范

将设计稿/HTML 转为 iOS 原生视图（UIView、UILabel、UIImageView 等）时的结构、样式、交互与验证要求。

## When to Use

- 将 HTML/index.html 转为 Objective-C 时

## Instructions
**文件结构要求**：
- 如果用户要求了文件结构或者修改范围，以用户要求的为准
### 图片资源处理
1.在index.html同级目录中如果存在多个images_{number}的文件夹{number}取之1～4，表示多种倍数的图。
2.需要放到Assets.xcassets 目录中，保证代码能正确引用
3.图片重命名：语义化,保持唯一性，不能和已存在的图片名称重名
### 布局实现
将flex布局转成Masonry实现的约束布局，如果用户非cocoapods工程或没有安装则在podfile中添加 `pod 'Masonry'`
### 组件实现
1.特殊处理：indexl.html中的CheckBox、RadioButton、Switch不能用image实现，需要转成iOS系统组件实现
2.循环组件使用 `UITableView` 或 `UICollectionView` 
3.组件识别并转成系统组件实现，添加交互件处理代码

### 样式完整性验证（⚠️ 强制要求）：
   - **必须验证**：对于每个元素，所有样式属性 = 原始行内样式的完整集合
   - **验证方法**：
     1. 提取原始行内样式的所有属性（包括 flexbox 属性：flexDirection、justifyContent、alignItems等）
     2. 转换为iOS的约束和属性
     3. 确保所有属性都完整且值精确匹配
   - **验证失败处理**：必须修复后重新验证，不能跳过

