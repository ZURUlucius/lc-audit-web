# CIPL Template Guide (CI+PL 模板说明)

## 模板文件

- **路径**: `C:\Users\jason.lzx\Desktop\Lucius\TARGET US\1.2. CIPL.xlsm`
- **格式**: Excel Macro-Enabled Workbook (.xlsm)
- **Sheet结构**: CI (Commercial Invoice) + PL (Packing List)

---

## CI Sheet (商业发票)

### Header 区域 (Row 1-13)

```
     A        B              C               D-F        G
 1        受益人名称
 2        受益人地址1
 3        受益人地址2
 4        受益人国家
 5
 6
 7   MESSRS:  申请人名称       DATE:         日期
 8           申请人地址1       INVOICE NO:   发票号
 9           申请人地址2       L/C NO.:      LC号
10           申请人国家
11
12
13  (表头标签行: DESCRIPTION / QUANTITY / UNIT PRICE / AMOUNT 等)
```

### Cell Mapping

| Cell | 内容 | 数据来源 | 备注 |
|------|------|---------|------|
| B1 | 受益人名称 | LC field 59 | 公司全称 |
| B2 | 受益人地址行1 | LC field 59 | 街道/门牌 |
| B3 | 受益人地址行2 | LC field 59 | 城市/邮编 |
| B4 | 受益人国家 | LC field 59 | 国名 |
| B7 | "MESSRS:" | 模板内置标签 | 固定文本，不需修改 |
| **C7** | **申请人名称** | **LC field 50** | **默认填LC申请人** |
| **C8** | **申请人地址行1** | **LC field 50** | |
| **C9** | **申请人地址行2** | **LC field 50** | |
| **C10** | **申请人国家** | **LC field 50** | |
| F7 | "DATE:" | 模板内置标签 | |
| G7 | 日期 | Invoice Date | 格式 DD-MMM-YYYY |
| F8 | "INVOICE NO:" | 模板内置标签 | |
| G8 | 发票号 | Invoice Number | |
| F9 | "L/C NO.:" | 模板内置标签 | |
| G9 | LC号 | LC Number | |

### Data 区域 (Row 14-60)

- Row 14: 表头行（DESCRIPTION, QUANTITY, UNIT PRICE, AMOUNT 等）
- Row 15-60: 数据行，每行一个品项
- Row 61: TOTAL 汇总行

### 合并单元格

CI sheet 的 C7-C10 区域可能涉及合并单元格（C7:F7, C8:F8, C9:F9, C10:F10），写入时需注意。

---

## PL Sheet (装箱单)

### Header 区域 (Row 1-14)

```
     A        B              C               O          P
 1        受益人名称
 2        受益人地址1
 3        受益人地址2
 4
 5
 6
 7   MESSRS:  =CI!C7         DATE:         日期
 8           =CI!C8          INVOICE NO:   发票号
 9           =CI!C9          L/C NO.:      LC号
10           =CI!C10
11
12
13
14  (表头标签行)
```

### Cell Mapping

| Cell | 内容 | 数据来源 | 备注 |
|------|------|---------|------|
| B1 | 受益人名称 | LC field 59 | |
| B2 | 受益人地址行1 | LC field 59 | |
| B3 | 受益人地址行2 | LC field 59 | |
| C7 | =CI!C7 | 公式引用CI sheet | 自动同步申请人名称 |
| C8 | =CI!C8 | 公式引用CI sheet | 自动同步申请人地址1 |
| C9 | =CI!C9 | 公式引用CI sheet | 自动同步申请人地址2 |
| C10 | =CI!C10 | 公式引用CI sheet | 自动同步申请人国家 |
| P7 | 日期 | Invoice Date | 格式 DD-MMM-YYYY |
| P8 | 发票号 | Invoice Number | |
| P9 | LC号 | LC Number | |

### Data 区域 (Row 15+)

- Row 15+: 数据行，含品名/数量/箱数/毛重/净重/尺码等
- R列: Container (集装箱号)

---

## 申请人显示规则

### 默认行为
- C7-C10 填入 LC field 50 的申请人信息
- 如果申请人名称/地址超过3行，需要合理拆分到C7-C10

### 特殊情况
- 如果LC条款（46A/47A）对发票抬头有特别要求（如要求显示其他收货方），按条款调整
- 需要人工判断时，应提示用户确认

---

## .xlsm 生成技术要点

### openpyxl 处理 .xlsm 的已知问题

1. **VBA丢失**: openpyxl 的 `save()` 在 `keep_vba=True` 时会保留 VBA，但可能丢失其他组件
2. **calcChain.xml 丢失**: 导致 Excel 打开时公式不自动计算
3. **printerSettings 丢失**: 打印设置丢失
4. **sharedStrings.xml 冲突**: openpyxl 使用内联字符串，不生成 sharedStrings.xml；保留模板的会导致修复提示

### ZIP层级修补策略

1. openpyxl 修改数据后保存为临时 .xlsx（keep_vba=True）
2. 以 openpyxl 输出为主体
3. 从模板注入缺失组件：calcChain.xml、printerSettings、metadata.xml
4. 从模板的 Content_Types.xml 和 workbook.xml.rels 注入 VBA 和 calcChain 引用
5. **不要**保留模板的 sharedStrings.xml
6. Content_Types.xml 中同一 Extension 只能有一个 Default 条目

---

## 更新记录

- 2026-04-21: 初始创建，记录 CI/PL sheet 的完整布局映射
- 2026-04-21: 确认申请人区域 C7-C10 默认填入 LC field 50 申请人信息
