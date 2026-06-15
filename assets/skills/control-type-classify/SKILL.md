---
name:control-type-classify
description: 控件分类。根据vlm_result.json中的控件类型，给index.html中的数据打上类型标记
---
## When to Use

- 将 index.html需要标记控件类型的时候

## Instructions
 
如果vlm_result.json中的type字段为Tabbar、BottomBar、Button、CheckBox、Radio、Switch、ImagePicker、Calender、Input，则在index.html中匹配到对应控件类型后，增加data-controltype类型标记



